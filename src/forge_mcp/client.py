"""MCP client connections for approved local and remote servers."""

from __future__ import annotations

import asyncio
import json
import webbrowser
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs, urlsplit

from forge_mcp.config import MCPConnection
from forge_mcp.vault import CredentialVault


class MCPConnectionError(RuntimeError):
    """A connection could not be established or safely used."""


class MCPConnector:
    """Connects to explicitly enabled MCP servers using the official Python SDK."""

    def __init__(self, vault: CredentialVault | None = None) -> None:
        self.vault = vault or CredentialVault()

    @asynccontextmanager
    async def _connected(self, connection: MCPConnection):
        if not connection.enabled:
            raise MCPConnectionError(f"{connection.name} is disabled. Enable it after reviewing the server.")
        try:
            from mcp import Client, StdioServerParameters
        except ImportError as exc:
            raise MCPConnectionError('Install the MCP SDK with: pip install "mcp>=2,<3"') from exc

        if connection.transport == "stdio":
            environment = {
                name: self.vault.get(reference)
                for name, reference in (connection.env_refs or {}).items()
            }
            parameters = StdioServerParameters(
                command=connection.command,
                args=list(connection.args),
                env=environment or None,
                cwd=connection.cwd,
            )
            async with Client(parameters) as client:
                yield client
            return

        if not connection.url:
            raise MCPConnectionError(f"{connection.name} has no remote endpoint URL.")

        try:
            import httpx2
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise MCPConnectionError("The installed MCP SDK does not expose Streamable HTTP support.") from exc

        if connection.auth_mode == "oauth":
            oauth, callback_server = await self._oauth_provider(connection)
            try:
                async with httpx2.AsyncClient(
                    auth=oauth,
                    timeout=httpx2.Timeout(30.0, read=300.0),
                ) as http_client:
                    transport = streamable_http_client(connection.url, http_client=http_client)
                    async with Client(transport) as client:
                        yield client
            finally:
                callback_server.close()
                await callback_server.wait_closed()
            return

        headers: dict[str, str] = {}
        for header, reference in (connection.header_refs or {}).items():
            value = self.vault.get(reference)
            if header.lower() == "authorization" and connection.auth_mode == "bearer":
                value = value if value.lower().startswith("bearer ") else f"Bearer {value}"
            headers[header] = value

        async with httpx2.AsyncClient(
            headers=headers,
            timeout=httpx2.Timeout(30.0, read=300.0),
        ) as http_client:
            transport = streamable_http_client(connection.url, http_client=http_client)
            async with Client(transport) as client:
                yield client

    async def _oauth_provider(self, connection: MCPConnection):
        """Build an OAuth 2.1 + PKCE flow with a loopback-only callback."""
        try:
            import httpx2
            from pydantic import AnyUrl
            from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider
            from mcp.client.streamable_http import streamable_http_client
            from mcp.shared.auth import OAuthClientMetadata
            from forge_mcp.oauth_storage import KeyringOAuthStorage
        except ImportError as exc:
            raise MCPConnectionError("OAuth requires the official MCP Python SDK v2.") from exc

        del httpx2, streamable_http_client
        loop = asyncio.get_running_loop()
        callback_result: asyncio.Future[AuthorizationCodeResult] = loop.create_future()

        async def callback_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                request = await asyncio.wait_for(reader.readline(), timeout=10)
                parts = request.decode("ascii", errors="replace").strip().split(" ")
                target = parts[1] if len(parts) >= 2 else "/"
                parsed = urlsplit(target)
                if parsed.path != "/callback":
                    writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                    await writer.drain()
                    return
                params = parse_qs(parsed.query)
                if "error" in params:
                    error = params.get("error_description", params["error"])[0]
                    if not callback_result.done():
                        callback_result.set_exception(MCPConnectionError(f"OAuth authorization failed: {error}"))
                elif "code" in params:
                    result = AuthorizationCodeResult(
                        code=params["code"][0],
                        state=params.get("state", [None])[0],
                        iss=params.get("iss", [None])[0],
                    )
                    if not callback_result.done():
                        callback_result.set_result(result)
                body = (
                    b"<!doctype html><title>Forge authorization</title>"
                    b"<h2>Forge authorization received</h2>"
                    b"<p>You can close this browser tab and return to your terminal.</p>"
                )
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                    + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii")
                    + body
                )
                await writer.drain()
            except Exception as exc:
                if not callback_result.done():
                    callback_result.set_exception(exc)
            finally:
                writer.close()
                await writer.wait_closed()

        callback_server = await asyncio.start_server(callback_handler, "127.0.0.1", 0)
        socket = callback_server.sockets[0]
        port = int(socket.getsockname()[1])
        redirect_uri = f"http://127.0.0.1:{port}/callback"

        async def redirect_handler(authorization_url: str) -> None:
            print("Opening the service authorization page in your browser.")
            opened = webbrowser.open(authorization_url, new=2, autoraise=True)
            if not opened:
                print(f"Open this URL to authorize Forge: {authorization_url}")

        async def wait_for_callback() -> AuthorizationCodeResult:
            return await asyncio.wait_for(callback_result, timeout=300)

        try:
            metadata_kwargs: dict[str, Any] = {
                "client_name": "Forge MCP",
                "redirect_uris": [AnyUrl(redirect_uri)],
            }
            if connection.oauth_scope:
                metadata_kwargs["scope"] = connection.oauth_scope
            oauth = OAuthClientProvider(
                server_url=connection.url,
                client_metadata=OAuthClientMetadata(**metadata_kwargs),
                storage=KeyringOAuthStorage(connection.name, self.vault),
                redirect_handler=redirect_handler,
                callback_handler=wait_for_callback,
            )
        except Exception:
            callback_server.close()
            await callback_server.wait_closed()
            raise
        return oauth, callback_server

    async def list_tools(self, connection: MCPConnection) -> list[dict[str, Any]]:
        async with self._connected(connection) as client:
            result = await client.list_tools()
            return [
                {
                    "name": tool.name,
                    "title": getattr(tool, "title", None),
                    "description": tool.description or "",
                    "input_schema": tool.input_schema,
                }
                for tool in result.tools
            ]

    async def call_tool(
        self,
        connection: MCPConnection,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        if connection.allowed_tools and tool_name not in connection.allowed_tools:
            raise MCPConnectionError(
                f"Tool {tool_name!r} is not in the allowlist for {connection.name!r}."
            )
        async with self._connected(connection) as client:
            result = await client.call_tool(tool_name, arguments)
        payload: dict[str, Any] = {"is_error": result.is_error}
        if result.structured_content is not None:
            payload["structured_content"] = result.structured_content
        else:
            payload["content"] = [
                {"type": getattr(item, "type", "unknown"), "text": getattr(item, "text", "")}
                for item in result.content
            ]
        return json.dumps(payload, ensure_ascii=False, default=str)
