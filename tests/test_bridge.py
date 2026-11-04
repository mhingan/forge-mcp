from __future__ import annotations

import asyncio

import pytest

from forge_mcp.bridge import MCPToolBridge
from forge_mcp.config import MCPConnection


class FakeStore:
    def __init__(self, connections: dict[str, MCPConnection]) -> None:
        self.connections = connections

    def load(self) -> dict[str, MCPConnection]:
        return dict(self.connections)


class FakeConnector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    async def list_tools(self, connection: MCPConnection) -> list[dict]:
        return [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write a file",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]

    async def call_tool(self, connection: MCPConnection, tool_name: str, arguments: dict) -> str:
        self.calls.append((connection.name, tool_name, arguments))
        return '{"ok": true}'


def connection(*, enabled: bool = True, allowed_tools: tuple[str, ...] = ()) -> MCPConnection:
    return MCPConnection(
        name="filesystem",
        transport="stdio",
        enabled=enabled,
        command="npx",
        args=("-y", "example-mcp"),
        allowed_tools=allowed_tools,
    )


def test_bridge_exposes_only_enabled_connections_and_allowed_tools() -> None:
    store = FakeStore(
        {
            "filesystem": connection(enabled=True, allowed_tools=("read_file",)),
            "disabled": MCPConnection(
                name="disabled",
                transport="stdio",
                enabled=False,
                command="npx",
                args=("disabled-server",),
            ),
        }
    )
    bridge = MCPToolBridge(store=store, connector=FakeConnector())

    schemas = asyncio.run(bridge.tool_schemas())

    assert [item["name"] for item in schemas] == ["mcp_filesystem_read_file"]


def test_bridge_rechecks_connection_enablement_before_tool_call() -> None:
    store = FakeStore({"filesystem": connection(enabled=True)})
    connector = FakeConnector()
    bridge = MCPToolBridge(store=store, connector=connector)

    asyncio.run(bridge.tool_schemas())
    store.connections["filesystem"] = connection(enabled=False)

    with pytest.raises(ValueError, match="disabled or removed"):
        asyncio.run(bridge.execute_tool("mcp_filesystem_read_file", {"path": "README.md"}))
    assert connector.calls == []


def test_bridge_rechecks_tool_allowlist_before_tool_call() -> None:
    store = FakeStore({"filesystem": connection(enabled=True)})
    connector = FakeConnector()
    bridge = MCPToolBridge(store=store, connector=connector)

    asyncio.run(bridge.tool_schemas())
    store.connections["filesystem"] = connection(enabled=True, allowed_tools=("write_file",))

    with pytest.raises(ValueError, match="allowlist"):
        asyncio.run(bridge.execute_tool("mcp_filesystem_read_file", {"path": "README.md"}))
    assert connector.calls == []


def test_bridge_calls_only_the_tool_that_was_discovered() -> None:
    store = FakeStore({"filesystem": connection(enabled=True)})
    connector = FakeConnector()
    bridge = MCPToolBridge(store=store, connector=connector)

    asyncio.run(bridge.tool_schemas())
    result = asyncio.run(
        bridge.execute_tool("mcp_filesystem_read_file", {"path": "README.md"})
    )

    assert result == '{"ok": true}'
    assert connector.calls == [("filesystem", "read_file", {"path": "README.md"})]
