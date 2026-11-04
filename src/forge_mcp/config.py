"""Atomic, secret-free local MCP connection manifest."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
CONFIG_VERSION = 1
PROTECTED_ENV = {
    "PATH", "HOME", "USERPROFILE", "APPDATA", "TMPDIR", "TEMP", "TMP",
    "SYSTEMROOT", "WINDIR", "NODE_OPTIONS", "PYTHONPATH", "PYTHONHOME",
    "LD_PRELOAD", "DYLD_INSERT_LIBRARIES",
}


@dataclass(frozen=True)
class MCPConnection:
    name: str
    transport: str
    enabled: bool = False
    command: str | None = None
    args: tuple[str, ...] = ()
    cwd: str | None = None
    url: str | None = None
    env_refs: dict[str, str] | None = None
    header_refs: dict[str, str] | None = None
    allowed_tools: tuple[str, ...] = ()
    source: str = "custom"

    @classmethod
    def from_dict(cls, name: str, value: dict[str, Any]) -> MCPConnection:
        transport = value.get("transport")
        if transport not in {"stdio", "http"}:
            raise ValueError(f"{name}: transport must be 'stdio' or 'http'.")
        command = value.get("command")
        url = value.get("url")
        if transport == "stdio" and (not isinstance(command, str) or not command.strip()):
            raise ValueError(f"{name}: stdio connections require a command.")
        if transport == "http":
            parsed = urlsplit(url or "")
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError(f"{name}: remote MCP connections must use HTTPS without embedded credentials.")
        enabled = value.get("enabled", False)
        if not isinstance(enabled, bool):
            raise TypeError(f"{name}: enabled must be a boolean.")
        args = value.get("args", [])
        if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            raise ValueError(f"{name}: args must be a list of strings.")
        env_refs = value.get("env_refs", {})
        header_refs = value.get("header_refs", {})
        if not isinstance(env_refs, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in env_refs.items()
        ):
            raise ValueError(f"{name}: env_refs must map environment names to keyring references.")
        if not isinstance(header_refs, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in header_refs.items()
        ):
            raise ValueError(f"{name}: header_refs must map header names to keyring references.")
        if any(not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) for key in env_refs):
            raise ValueError(f"{name}: env_refs contains an invalid environment variable name.")
        if set(env_refs) & PROTECTED_ENV:
            raise ValueError(f"{name}: env_refs cannot override protected process environment variables.")
        if any(not re.fullmatch(r"[A-Za-z0-9-]+", key) for key in header_refs):
            raise ValueError(f"{name}: header_refs contains an invalid HTTP header name.")
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,190}", ref) for ref in [*env_refs.values(), *header_refs.values()]):
            raise ValueError(f"{name}: a credential reference contains unsupported characters.")
        allowed_tools = value.get("allowed_tools", [])
        if not isinstance(allowed_tools, list) or not all(isinstance(x, str) for x in allowed_tools):
            raise ValueError(f"{name}: allowed_tools must be a list of strings.")
        return cls(
            name=name,
            transport=transport,
            enabled=enabled,
            command=command,
            args=tuple(args),
            cwd=value.get("cwd"),
            url=url,
            env_refs=env_refs,
            header_refs=header_refs,
            allowed_tools=tuple(allowed_tools),
            source=str(value.get("source", "custom")),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "transport": self.transport,
            "enabled": self.enabled,
            "args": list(self.args),
            "env_refs": self.env_refs or {},
            "header_refs": self.header_refs or {},
            "allowed_tools": list(self.allowed_tools),
            "source": self.source,
        }
        for key in ("command", "cwd", "url"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


class ConnectionStore:
    """Stores only server metadata; actual credentials belong in the OS keyring."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (Path.home() / ".forge" / "mcp.json")

    def load(self) -> dict[str, MCPConnection]:
        if self.path.parent.is_symlink():
            raise ValueError(f"Refusing to read config through a symlinked directory: {self.path.parent}")
        if not self.path.exists():
            return {}
        if self.path.is_symlink():
            raise ValueError(f"Refusing to read symlinked MCP config: {self.path}")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != CONFIG_VERSION:
            raise ValueError("Unsupported or malformed Forge MCP config.")
        entries = payload.get("servers", {})
        if not isinstance(entries, dict):
            raise TypeError("Forge MCP config 'servers' must be an object.")
        return {name: MCPConnection.from_dict(name, value) for name, value in entries.items()}

    def save(self, connections: dict[str, MCPConnection]) -> None:
        if self.path.parent.is_symlink():
            raise ValueError(f"Refusing to write config through a symlinked directory: {self.path.parent}")
        for name in connections:
            if not NAME_RE.fullmatch(name):
                raise ValueError(f"Invalid MCP connection name: {name!r}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        payload = {
            "version": CONFIG_VERSION,
            "servers": {name: item.to_dict() for name, item in sorted(connections.items())},
        }
        encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".mcp-config-", delete=False,
            ) as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if temporary_name and os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def add(self, connection: MCPConnection, replace: bool = False) -> None:
        connections = self.load()
        if connection.name in connections and not replace:
            raise ValueError(f"{connection.name!r} already exists. Use replace=True to update it.")
        connections[connection.name] = connection
        self.save(connections)

    def remove(self, name: str) -> None:
        connections = self.load()
        if name not in connections:
            raise ValueError(f"Unknown MCP connection: {name}")
        del connections[name]
        self.save(connections)

    def set_enabled(self, name: str, enabled: bool) -> None:
        connections = self.load()
        if name not in connections:
            raise ValueError(f"Unknown MCP connection: {name}")
        current = connections[name]
        values = current.to_dict()
        values["enabled"] = enabled
        connections[name] = MCPConnection.from_dict(name, values)
        self.save(connections)
