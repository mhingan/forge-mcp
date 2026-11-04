"""Forge MCP discovery and local connection configuration."""

from forge_mcp.config import ConnectionStore, MCPConnection
from forge_mcp.popular import popular_servers, popularity_metadata
from forge_mcp.registry import MCPRegistry, ServerRecord

__all__ = ["ConnectionStore", "MCPConnection", "MCPRegistry", "ServerRecord", "popular_servers", "popularity_metadata"]
__version__ = "0.1.0"
