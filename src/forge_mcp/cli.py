"""Command-line interface for Forge MCP."""

from __future__ import annotations

import argparse
import json
import sys

from forge_mcp.config import ConnectionStore, MCPConnection
from forge_mcp.registry import MCPRegistry


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge-mcp", description="Discover and configure MCP servers.")
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search", help="Search the official MCP Registry")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=25)
    browse = sub.add_parser("browse", help="Browse the official MCP Registry")
    browse.add_argument("--limit", type=int, default=100)
    local = sub.add_parser("list", help="List local MCP connections")
    local.add_argument("--json", action="store_true")
    add = sub.add_parser("add-http", help="Add a remote HTTPS MCP server (disabled by default)")
    add.add_argument("name")
    add.add_argument("url")
    add.add_argument("--enable", action="store_true")
    stdio = sub.add_parser("add-stdio", help="Add a local STDIO MCP server (disabled by default)")
    stdio.add_argument("name")
    stdio.add_argument("command")
    stdio.add_argument("args", nargs="*")
    stdio.add_argument("--enable", action="store_true")
    remove = sub.add_parser("remove", help="Remove a local connection")
    remove.add_argument("name")
    enable = sub.add_parser("enable", help="Enable a connection after reviewing its permissions")
    enable.add_argument("name")
    disable = sub.add_parser("disable", help="Disable a connection")
    disable.add_argument("name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ConnectionStore()
    try:
        if args.command == "search":
            _print_records(MCPRegistry().search(args.query, args.limit))
        elif args.command == "browse":
            _print_records(MCPRegistry().browse(args.limit))
        elif args.command == "list":
            connections = store.load()
            if args.json:
                print(json.dumps({name: item.to_dict() for name, item in connections.items()}, indent=2))
            else:
                for name, item in connections.items():
                    state = "enabled" if item.enabled else "disabled"
                    target = item.url if item.transport == "http" else item.command
                    print(f"{name:<24} {item.transport:<6} {state:<9} {target}")
        elif args.command == "add-http":
            if not args.url.startswith("https://"):
                raise ValueError("Remote MCP endpoints must use HTTPS.")
            store.add(MCPConnection(name=args.name, transport="http", enabled=args.enable, url=args.url))
            print(f"Added {args.name}. Review it, add credential references, then enable it.")
        elif args.command == "add-stdio":
            store.add(MCPConnection(name=args.name, transport="stdio", enabled=args.enable,
                                    command=args.command, args=tuple(args.args)))
            print(f"Added {args.name}. Local commands execute on this computer when enabled.")
        elif args.command == "remove":
            store.remove(args.name)
            print(f"Removed {args.name}.")
        elif args.command in {"enable", "disable"}:
            store.set_enabled(args.name, args.command == "enable")
            print(f"{args.name}: {args.command}d.")
        return 0
    except Exception as exc:
        print(f"forge-mcp: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
