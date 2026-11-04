"""Read-only client for the official MCP Registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_REGISTRY_URL = "https://registry.modelcontextprotocol.io"
DEFAULT_TIMEOUT = 20.0


@dataclass(frozen=True)
class ServerRecord:
    """Normalized view of an official registry server version."""

    name: str
    description: str = ""
    version: str = ""
    status: str = "unknown"
    packages: tuple[dict[str, Any], ...] = ()
    remotes: tuple[dict[str, Any], ...] = ()
    repository: str | None = None
    raw: dict[str, Any] | None = None

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> ServerRecord:
        server = item.get("server") if isinstance(item.get("server"), dict) else item
        repository = server.get("repository")
        if isinstance(repository, dict):
            repository_url = repository.get("url")
        elif isinstance(repository, str):
            repository_url = repository
        else:
            repository_url = None
        return cls(
            name=str(server.get("name") or ""),
            description=str(server.get("description") or ""),
            version=str(item.get("version") or server.get("version") or ""),
            status=str(item.get("status") or "active"),
            packages=tuple(p for p in server.get("packages", []) if isinstance(p, dict)),
            remotes=tuple(r for r in server.get("remotes", []) if isinstance(r, dict)),
            repository=repository_url,
            raw=item,
        )


class MCPRegistry:
    """Search and browse the public, read-only MCP Registry API.

    Registry metadata is untrusted input. It is never executed by this package.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_REGISTRY_URL,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._client is not None:
            response = self._client.get(f"{self.base_url}{path}", params=params)
        else:
            response = httpx.get(
                f"{self.base_url}{path}", params=params, timeout=self.timeout,
                follow_redirects=False,
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("MCP Registry returned an unexpected response.")
        return payload

    def search(self, query: str, limit: int = 25) -> list[ServerRecord]:
        query = query.strip()
        if len(query) < 3:
            raise ValueError("Registry search requires at least three characters.")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        payload = self._get(
            "/v0.1/servers",
            {"search": query, "version": "latest", "limit": limit},
        )
        return self._records(payload)

    def browse(self, limit: int = 100) -> list[ServerRecord]:
        """Return up to 100 records from the official registry (alphabetical API order)."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        payload = self._get("/v0.1/servers", {"version": "latest", "limit": limit})
        records = self._records(payload)
        cursor = (payload.get("metadata") or {}).get("nextCursor")
        while cursor and len(records) < limit:
            page = self._get(
                "/v0.1/servers",
                {"version": "latest", "limit": min(100, limit - len(records)), "cursor": cursor},
            )
            records.extend(self._records(page))
            cursor = (page.get("metadata") or {}).get("nextCursor")
        return records[:limit]

    def get(self, name: str) -> ServerRecord:
        if not name.strip():
            raise ValueError("Server name is required.")
        encoded = quote(name.strip(), safe="")
        payload = self._get(f"/v0.1/servers/{encoded}/versions/latest", {})
        item = payload.get("server") if isinstance(payload.get("server"), dict) else payload
        record = ServerRecord.from_api(item if "server" in item else payload)
        if not record.name:
            raise ValueError(f"Registry response for {name!r} did not contain a server name.")
        return record

    @staticmethod
    def _records(payload: dict[str, Any]) -> list[ServerRecord]:
        items = payload.get("servers", [])
        if not isinstance(items, list):
            raise TypeError("MCP Registry response has no valid servers list.")
        records: list[ServerRecord] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            record = ServerRecord.from_api(item)
            if record.name and record.name not in seen and record.status != "deleted":
                seen.add(record.name)
                records.append(record)
        return records
