"""Command-line interface for Forge MCP."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys

import httpx

from forge_mcp.client import MCPConnector
from forge_mcp.config import ConnectionStore, MCPConnection
from forge_mcp.popular import popular_servers, popularity_metadata
from forge_mcp.registry import MCPRegistry
from forge_mcp.vault import CredentialVault


def _print_records(records) -> None:
    if not records:
        print("No MCP servers found.")
        return
    for record in records:
        kinds = []
        if record.packages:
            kinds.append("package")
        if record.remotes:
            kinds.append("remote")
        print(f"{record.name} [{', '.join(kinds) or 'metadata only'}]")
        if record.description:
            print(f"  {record.description[:180]}")
        if record.repository:
            print(f"  Repository: {record.repository}")


def _parse_refs(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        name, separator, reference = value.partition("=")
        if not separator or not name or not reference:
            raise ValueError(f"Expected NAME=KEYRING_REFERENCE, received {value!r}.")
        if name in result:
            raise ValueError(f"Duplicate credential mapping for {name!r}.")
        result[name] = reference
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forge-mcp",
        description="Discover, approve, and connect MCP servers for Forge.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search the official MCP Registry")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=25)

    browse = sub.add_parser("browse", help="Browse the official MCP Registry")
    browse.add_argument("--limit", type=int, default=100)

    popular = sub.add_parser("popular", help="List popular MCP servers by GitHub stars")
    popular.add_argument("--limit", type=int, default=100)

    local = sub.add_parser("list", help="List local MCP connections")
    local.add_argument("--json", action="store_true")

    add = sub.add_parser("add-http", help="Add a remote HTTPS MCP server, disabled by default")
    add.add_argument("name")
    add.add_argument("url")
    add.add_argument("--auth-mode", choices=["none", "bearer", "oauth"], default="none")
    add.add_argument("--scope", help="OAuth scopes, space separated")
    add.add_argument("--credential-ref", help="Keyring reference for a bearer token")
    add.add_argument(
        "--header-ref",
        action="append",
        default=[],
        metavar="HEADER=KEYRING_REF",
        help="Map an HTTP header to a keyring reference; repeat for multiple headers",
    )
    add.add_argument("--enable", action="store_true", help="Enable immediately after explicit review")

    stdio = sub.add_parser("add-stdio", help="Add a local STDIO MCP server, disabled by default")
    stdio.add_argument("name")
    stdio.add_argument("executable")
    stdio.add_argument("args", nargs="*")
    stdio.add_argument("--cwd")
    stdio.add_argument("--env-ref", action="append", default=[], metavar="ENV=KEYRING_REF")
    stdio.add_argument("--allow-tool", action="append", default=[])
    stdio.add_argument("--enable", action="store_true")

    enable = sub.add_parser("enable", help="Enable a connection after reviewing its permissions")
    enable.add_argument("name")
    enable.add_argument("--yes", action="store_true", help="Confirm the trust decision non-interactively")

    disable = sub.add_parser("disable", help="Disable a connection without deleting credentials")
    disable.add_argument("name")

    remove = sub.add_parser("remove", help="Remove a local connection manifest entry")
    remove.add_argument("name")

    credential = sub.add_parser("credential", help="Manage secrets in the OS credential store")
    credential_sub = credential.add_subparsers(dest="credential_command", required=True)
    credential_set = credential_sub.add_parser("set", help="Store a secret without echoing it")
    credential_set.add_argument("reference")
    credential_delete = credential_sub.add_parser("delete", help="Delete a secret")
    credential_delete.add_argument("reference")

    tools = sub.add_parser("tools", help="Discover tools exposed by an enabled MCP server")
    tools.add_argument("name")

    call = sub.add_parser("call", help="Call a tool on an enabled MCP server")
    call.add_argument("name")
    call.add_argument("tool")
    call.add_argument("--arguments", default="{}", help="JSON object containing tool arguments")

    sub.add_parser("serve", help="Run the local stdio gateway for Copilot and other MCP hosts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ConnectionStore()
    try:
        if args.command == "search":
            _print_records(MCPRegistry().search(args.query, args.limit))
        elif args.command == "browse":
            _print_records(MCPRegistry().browse(args.limit))
        elif args.command == "popular":
            metadata = popularity_metadata()
            print(f"{metadata['title']} — snapshot {metadata['snapshot_date']}")
            print(f"Ranking: {metadata['ranking_method']}")
            print(f"Source: {metadata['source']}")
            print(metadata["caveat"])
            for item in popular_servers(args.limit):
                print(
                    f"{item['rank']:>3}. {item['name']} ({item['publisher']}) "
                    f"— {item['github_stars']:,} stars"
                )
        elif args.command == "list":
            connections = store.load()
            if args.json:
                print(json.dumps(
                    {name: item.to_dict() for name, item in connections.items()},
                    indent=2,
                    ensure_ascii=False,
                ))
            else:
                for name, item in connections.items():
                    state = "enabled" if item.enabled else "disabled"
                    target = item.url if item.transport == "http" else item.command
                    print(f"{name:<24} {item.transport:<6} {state:<9} {target}")
        elif args.command == "add-http":
            header_refs = _parse_refs(args.header_ref)
            if args.credential_ref:
                if "Authorization" in header_refs:
                    raise ValueError("Do not provide Authorization twice.")
                header_refs["Authorization"] = args.credential_ref
            if args.auth_mode == "bearer" and "Authorization" not in header_refs:
                raise ValueError(
                    "Bearer auth requires --credential-ref or --header-ref Authorization=REFERENCE."
                )
            if args.auth_mode == "oauth" and header_refs:
                raise ValueError("OAuth cannot be combined with static HTTP header references.")
            connection = MCPConnection(
                name=args.name,
                transport="http",
                enabled=args.enable,
                url=args.url,
                auth_mode=args.auth_mode,
                oauth_scope=args.scope,
                header_refs=header_refs,
            )
            store.add(connection)
            print(f"Added {args.name} (enabled={args.enable}).")
            print("Remote endpoints require HTTPS and are contacted only when enabled.")
        elif args.command == "add-stdio":
            connection = MCPConnection(
                name=args.name,
                transport="stdio",
                enabled=args.enable,
                command=args.executable,
                args=tuple(args.args),
                cwd=args.cwd,
                env_refs=_parse_refs(args.env_ref),
                allowed_tools=tuple(args.allow_tool),
            )
            store.add(connection)
            print(f"Added {args.name} (enabled={args.enable}).")
            print("Enabling a STDIO server permits its command to execute locally.")
        elif args.command == "enable":
            connection = store.load().get(args.name)
            if connection is None:
                raise ValueError(f"Unknown MCP connection: {args.name}")
            if not args.yes:
                target = connection.url if connection.transport == "http" else (
                    f"{connection.command} {' '.join(connection.args)}"
                )
                print(f"Server: {args.name}")
                print(f"Transport: {connection.transport}")
                print(f"Target: {target}")
                print("Only enable servers whose publisher, package, endpoint and tools you trust.")
                if input("Trust and enable this MCP server? [y/N] ").strip().lower() not in {"y", "yes"}:
                    print("No changes made.")
                    return 0
            store.set_enabled(args.name, True)
            print(f"{args.name} enabled.")
        elif args.command == "disable":
            store.set_enabled(args.name, False)
            print(f"{args.name} disabled.")
        elif args.command == "remove":
            store.remove(args.name)
            print(f"Removed {args.name}. Stored credentials are retained; delete them separately.")
        elif args.command == "credential":
            vault = CredentialVault()
            if args.credential_command == "set":
                secret = getpass.getpass(f"Secret for {args.reference}: ")
                confirmation = getpass.getpass("Confirm secret: ")
                if not secret or secret != confirmation:
                    raise ValueError("Credential was empty or the confirmation did not match.")
                vault.set(args.reference, secret)
                print(f"Saved {args.reference} in the OS credential store.")
            else:
                vault.delete(args.reference)
                print(f"Deleted {args.reference} from the OS credential store.")
        elif args.command == "tools":
            connection = store.load().get(args.name)
            if connection is None:
                raise ValueError(f"Unknown MCP connection: {args.name}")
            records = asyncio.run(MCPConnector().list_tools(connection))
            print(json.dumps(records, indent=2, ensure_ascii=False, default=str))
        elif args.command == "call":
            connection = store.load().get(args.name)
            if connection is None:
                raise ValueError(f"Unknown MCP connection: {args.name}")
            arguments = json.loads(args.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("--arguments must decode to a JSON object.")
            result = asyncio.run(MCPConnector().call_tool(connection, args.tool, arguments))
            print(result)
        elif args.command == "serve":
            from forge_mcp.gateway import run
            run()
        return 0
    except (ValueError, OSError, TypeError, KeyError, json.JSONDecodeError, httpx.HTTPError) as exc:
        print(f"forge-mcp: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"forge-mcp: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
