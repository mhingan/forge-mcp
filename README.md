# Forge MCP

A secure MCP integration registry and connection manager for the Forge ecosystem.

Forge MCP discovers MCP servers from the official Model Context Protocol Registry, maintains a local connection manifest, and exposes curated integration metadata. Forge Runtime consumes this package to start approved MCP connections and make their tools available to agents.

## Install

```bash
python -m pip install forge-mcp
```

## Search the official registry

```bash
forge-mcp search figma
forge-mcp browse --limit 100
forge-mcp list
```

## Configuration

Connections are stored in `~/.forge/mcp.json` with restrictive file permissions. Credentials are intentionally not written to this file; Forge Runtime stores them in the operating-system credential store.

## Trust model

Registry entries are metadata, not trusted executable code. Local STDIO servers execute on the user's machine. Review their publisher, package, permissions, and requested credentials before enabling them. Remote servers are contacted only after the user explicitly adds and enables them.

The package does not claim that all registry entries are verified or safe. Registry provenance and package metadata must be reviewed before installation.

## License

MIT.
