#!/usr/bin/env python3
"""Foundry memory MCP server (Phase 1 skeleton).

Exposes the `foundry-memory` tools (memory.read/write, rag.index) over MCP, backed
by Postgres + Qdrant + Redis. This skeleton defines the surface; wire the stores
per docs/06-memory-system.md. Run via: python3 -m services.memory.server
"""
from __future__ import annotations

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # mcp not installed yet
    FastMCP = None

INSTRUCTIONS = "Foundry durable memory: working / semantic / project / code / decision."


def build():
    if FastMCP is None:
        raise SystemExit("Install deps first: pip install -r requirements.txt")
    mcp = FastMCP("foundry-memory", instructions=INSTRUCTIONS)

    @mcp.tool()
    def memory_read(query: str, classes: str = "project,decision", top_k: int = 8) -> str:
        """Retrieve context via the RAG pipeline (docs/06). TODO: hybrid search + rerank."""
        return "TODO: hybrid search over [" + classes + "] for: " + query

    @mcp.tool()
    def memory_write(kind: str, content: str, project: str = "") -> str:
        """Persist a durable fact/decision (NOT chat). Decisions go to the append-only log."""
        return "TODO: persist " + kind + " (project=" + project + ", " + str(len(content)) + " chars)"

    @mcp.tool()
    def rag_index(path: str) -> str:
        """(Re)index a repo/doc path into Qdrant. TODO: chunk + embed + upsert."""
        return "TODO: index " + path

    return mcp


if __name__ == "__main__":
    build().run()
