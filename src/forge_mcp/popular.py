"""Curated popularity snapshot for MCP server discovery.

The rankings are a discovery aid, not a safety endorsement. Resolve every
candidate through the official MCP Registry and verify its publisher.
"""
from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def popular_servers(limit: int = 100) -> list[dict[str, Any]]:
    """Return the current bundled popularity snapshot, sorted by GitHub stars."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    source = files("forge_mcp").joinpath("data", "popular.json")
    payload = json.loads(source.read_text(encoding="utf-8"))
    entries = payload.get("servers")
    if not isinstance(entries, list):
        raise TypeError("Bundled MCP popularity catalogue is malformed.")
    return entries[:limit]


def popularity_metadata() -> dict[str, str]:
    """Return ranking methodology, snapshot date, and source."""
    source = files("forge_mcp").joinpath("data", "popular.json")
    payload = json.loads(source.read_text(encoding="utf-8"))
    return {
        "title": str(payload.get("title", "")),
        "snapshot_date": str(payload.get("snapshot_date", "")),
        "source": str(payload.get("source", "")),
        "ranking_method": str(payload.get("ranking_method", "")),
        "caveat": str(payload.get("caveat", "")),
    }
