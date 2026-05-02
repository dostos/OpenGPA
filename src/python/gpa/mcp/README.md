> **DEPRECATED** — The OpenGPA MCP server is deprecated in favor of the
> `gpa` CLI. Agents should call OpenGPA via their built-in shell tool
> against the noun-verb commands documented in
> [docs/cli/agent-integration.md](../../../docs/cli/agent-integration.md).
> Physical removal scheduled ~4 weeks after 2026-05-02.

# MCP Server

Model Context Protocol server for OpenGPA. Runs over stdio JSON-RPC and exposes 10 tools that proxy to the REST API, making OpenGPA's capture and query capabilities available to Claude Code and other MCP-compatible clients.

## Key Files
- `server.py` — stdio transport, tool dispatch loop
- `tools.py` — tool definitions and argument schemas
- `client.py` — internal HTTP client to the REST API

## See Also
- `src/python/gpa/api/README.md` — REST API being proxied
- Root `README.md` for MCP configuration instructions
