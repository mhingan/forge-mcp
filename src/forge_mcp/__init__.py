"""Forge MCP discovery, secure connections, and Runtime tool bridging."""

from forge_mcp.bridge import MCPToolBridge
from forge_mcp.client import MCPConnector, MCPConnectionError
from forge_mcp.config import ConnectionStore, MCPConnection
from forge_mcp.popular import popular_servers, popularity_metadata
from forge_mcp.registry import MCPRegistry, ServerRecord
from forge_mcp.vault import CredentialError, CredentialVault

__all__ = [
    "ConnectionStore",
    "CredentialError",
    "CredentialVault",
    "MCPConnection",
    "MCPConnectionError",
    "MCPConnector",
    "MCPRegistry",
    "MCPToolBridge",
    "ServerRecord",
    "popular_servers",
    "popularity_metadata",
]
__version__ = "0.2.0"
