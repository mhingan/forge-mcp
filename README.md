# Forge MCP

A secure MCP integration registry, connection manager, OAuth client, and local gateway for the Forge ecosystem.

Forge MCP discovers servers from the official Model Context Protocol Registry, maintains a local connection manifest, stores credentials in the operating-system keychain, and exposes approved MCP tools to Forge Runtime or any compatible MCP host.

The GitHub repository remains named forge-mcp. The PyPI distribution is forge-mcp-registry, because the forge-mcp distribution name is already occupied by an unrelated MCP testing package. The Python import remains forge_mcp.

## Install

    python -m pip install forge-mcp-registry

## Discover connectors

    forge-mcp search figma
    forge-mcp browse --limit 100
    forge-mcp popular --limit 100
    forge-mcp list

The official registry is the live source for server metadata, versions, and transports. The bundled 100-entry discovery snapshot is ranked by GitHub stars using MCP.Directory data dated 2026-11-03. Stars are not search counts, and popularity is not a security endorsement. Always resolve publisher and package metadata through the official registry before enabling a connector.

## Connect a remote OAuth MCP

    forge-mcp add-http figma https://mcp.figma.com/mcp --auth-mode oauth
    forge-mcp enable figma
    forge-mcp tools figma

The first connection opens the service authorization page. Forge uses the official MCP SDK OAuth 2.1 / PKCE provider and a loopback-only callback, persists OAuth tokens and client registration details in the OS credential store, and refreshes tokens through the SDK.

You can provide an OAuth scope when the service requires it:

    forge-mcp add-http my-service https://example.com/mcp --auth-mode oauth --scope "files:read projects:read"

## Connect a remote server using an API token

    forge-mcp add-http service https://mcp.example.com/mcp --auth-mode bearer --credential-ref forge/service/token
    forge-mcp credential set forge/service/token
    forge-mcp enable service
    forge-mcp tools service

The credential prompt does not echo the secret. The value is saved in macOS Keychain, Windows Credential Manager, or a configured Linux Secret Service backend. There is no plaintext-file fallback.

## Connect a local STDIO server

    forge-mcp add-stdio filesystem npx -y @modelcontextprotocol/server-filesystem /path/to/project
    forge-mcp enable filesystem
    forge-mcp tools filesystem

For local servers that require secrets, map an environment variable to a keyring reference:

    forge-mcp add-stdio my-server node server.js --env-ref MY_API_TOKEN=forge/my-server/token
    forge-mcp credential set forge/my-server/token

STDIO connections run local commands. They are disabled by default; only enable packages and commands you have reviewed. Arguments are passed as an argv array, never interpolated into a shell command.

## One gateway for Copilot and Forge Runtime

Configure your MCP host with one stdio server:

    {
      "mcpServers": {
        "forge": {
          "command": "forge-mcp",
          "args": ["serve"]
        }
      }
    }

The gateway exposes four tools:

- forge_mcp_list_servers — show configured connections and status.
- forge_mcp_search — search the official registry without installing anything.
- forge_mcp_list_tools — inspect tools on an enabled connection.
- forge_mcp_call_tool — call a tool on an enabled connection.

Forge Runtime imports MCPToolBridge to expose the same approved connections as function tools to its OpenAI and Anthropic providers.

## Local state and trust model

Connection metadata is stored in ~/.forge/mcp.json with restrictive permissions. Secrets and OAuth tokens are stored separately in the OS credential store; the JSON manifest contains only references.

Registry entries are untrusted metadata, not executable code. Remote servers are contacted only after explicit enablement. Local STDIO servers execute on the user's computer when enabled. Tool descriptions and results are untrusted model context. Keep allowed_tools constrained for servers that expose sensitive or destructive capabilities.

The package does not claim that registry entries are verified or safe. Review the publisher, package, endpoint, requested permissions, and tool list before enabling a server.

## License

MIT.
