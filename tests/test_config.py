from pathlib import Path

import pytest

from forge_mcp.config import ConnectionStore, MCPConnection


def test_config_roundtrip_and_permissions(tmp_path: Path):
    store = ConnectionStore(tmp_path / ".forge" / "mcp.json")
    connection = MCPConnection(
        name="figma", transport="stdio", enabled=False,
        command="npx", args=("-y", "figma-mcp"),
        env_refs={"FIGMA_TOKEN": "forge/figma/token"},
    )
    store.add(connection)
    loaded = store.load()["figma"]
    assert loaded.command == "npx"
    assert loaded.env_refs == {"FIGMA_TOKEN": "forge/figma/token"}
    assert loaded.enabled is False
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_remote_http_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        MCPConnection.from_dict("unsafe", {"transport": "http", "url": "http://example.com/mcp"})


def test_config_never_persists_secret_values(tmp_path: Path):
    store = ConnectionStore(tmp_path / "mcp.json")
    store.add(MCPConnection(
        name="test", transport="stdio", command="node",
        env_refs={"TOKEN": "forge/test/token"},
    ))
    text = store.path.read_text()
    assert "forge/test/token" in text
    assert "actual-secret-value" not in text


def test_remote_url_cannot_embed_credentials():
    with pytest.raises(ValueError, match="embedded credentials"):
        MCPConnection.from_dict(
            "unsafe",
            {"transport": "http", "url": "https://user:password@example.com/mcp"},
        )


def test_enabled_must_be_a_boolean():
    with pytest.raises(TypeError, match="enabled must be a boolean"):
        MCPConnection.from_dict(
            "unsafe",
            {"transport": "stdio", "command": "npx", "enabled": "false"},
        )
