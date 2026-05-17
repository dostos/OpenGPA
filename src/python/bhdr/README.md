# Beholder Python Package

Root of the `gpa` Python package. Provides the REST API, MCP server, capture backends, framework integration layer, and eval harness that together form the Beholder surface exposed to LLM agents.

## Key Subdirectories
- `api/` — FastAPI REST endpoints
- `mcp/` — MCP server (stdio JSON-RPC)
- `backends/` — capture backend abstraction (native + RenderDoc)
- `framework/` — framework metadata and correlation engine
- `eval/` — eval harness for measuring debugging effectiveness

## See Also
- `src/bindings/README.md` — native C++ bindings used by the backends
- Root `README.md` for project-level overview
