#!/usr/bin/env python3
"""Translate MCP tool definitions into something a small local model can actually use.

The official `mcp` SDK ships NO conversion helper - an exhaustive grep of all 122 modules in
mcp 2.0.0 finds zero occurrences of "openai", "ollama" or "to_openai". This adapter is the
integrator's work, and it is not optional, for two reasons:

1. MCP `inputSchema` is FULL JSON Schema (dialect 2020-12). SEP-2106, shipped in the
   2026-07-28 revision, removed the old type/properties/required restriction: a conformant
   server may legally emit `oneOf`, `anyOf`, `allOf`, `not`, `if`/`then`/`else`, `$ref`,
   `$defs`, `$anchor`. This is not theoretical - MCP servers derive schemas from Python type
   hints via Pydantic, so `Optional[str]` produces `anyOf` and any nested model produces
   `$defs`/`$ref` BY CONSTRUCTION. Every FastMCP-style server with one optional argument
   ships composition keywords, and Ollama's tool parser rejects several of them.

2. Tool-name collisions are unresolved at the protocol level. Uniqueness is scoped per
   server, disambiguation falls entirely on the aggregating client, and the spec explicitly
   warns that a server's own `serverInfo.name` is NOT unique and must not be used as the
   namespace key. The client has to mint its own stable prefixes.

Security note carried from the spec: implementations MUST NOT auto-dereference network
`$ref`s. A remote `$ref` is a server telling the client to go fetch something; this module
refuses them rather than resolving them.

This deliberately depends on nothing but the standard library, so it is testable without the
SDK installed and cannot break when the SDK's major version moves (it went 1.x -> 2.0.0 on
2026-07-28, and v2 renamed the attribute to snake_case `input_schema`).
"""
from __future__ import annotations

import re

# Keywords Ollama's parser understands. Everything else is dropped rather than passed
# through, because a schema it cannot parse fails the whole tool-call, not just the field.
KEEP_KEYS = {"type", "description", "enum", "items", "properties", "required",
             "default", "title", "minimum", "maximum", "minLength", "maxLength"}

# Composition keywords that must be resolved away before Ollama sees them.
COMPOSITION = ("anyOf", "oneOf", "allOf")

MAX_DEPTH = 12          # bounds composition cost, per the spec's SHOULD
NAME_RE = re.compile(r"[^a-zA-Z0-9_]")


class SchemaError(ValueError):
    """A schema cannot be safely reduced - the tool is skipped rather than sent malformed."""


def namespaced(prefix: str, tool_name: str) -> str:
    """Mint a stable, collision-proof tool name.

    Uses the client's own prefix for the server, never the server's self-reported name.
    Ollama tool names must look like identifiers, so anything else is flattened.
    """
    raw = f"{prefix}_{tool_name}" if prefix else tool_name
    cleaned = NAME_RE.sub("_", raw).strip("_")
    if not cleaned:
        raise SchemaError(f"tool name reduces to nothing: {tool_name!r}")
    return cleaned[:64]


def _pick_branch(branches, defs, depth):
    """Collapse anyOf/oneOf to a single usable branch.

    Pydantic renders Optional[X] as anyOf[X, null]. The null branch carries no information a
    model can act on, so the non-null branch IS the schema and optionality is already
    expressed by absence from `required`. Where several real branches exist we take the
    first and lose expressiveness - a deliberate trade: a model that cannot parse the schema
    calls nothing at all, which is worse than a model working from a narrowed one.
    """
    usable = [b for b in branches
              if isinstance(b, dict) and b.get("type") != "null" and b != {"type": "null"}]
    if not usable:
        raise SchemaError("composition had no non-null branch")
    return _reduce(usable[0], defs, depth + 1)


def _reduce(node, defs, depth=0):
    if depth > MAX_DEPTH:
        raise SchemaError(f"schema nested deeper than {MAX_DEPTH}")
    if not isinstance(node, dict):
        raise SchemaError(f"schema node is {type(node).__name__}, expected object")

    # --- references ------------------------------------------------------------
    ref = node.get("$ref")
    if ref:
        if not ref.startswith("#"):
            # The spec forbids auto-dereferencing network refs. Refusing is the safe read.
            raise SchemaError(f"refusing to dereference non-local $ref: {ref}")
        key = ref.rsplit("/", 1)[-1]
        target = defs.get(key)
        if target is None:
            raise SchemaError(f"unresolvable local $ref: {ref}")
        return _reduce(target, defs, depth + 1)

    # --- composition -----------------------------------------------------------
    for keyword in COMPOSITION:
        if keyword in node:
            branches = node[keyword]
            if keyword == "allOf":
                merged: dict = {"type": "object", "properties": {}, "required": []}
                for branch in branches:
                    part = _reduce(branch, defs, depth + 1)
                    merged["properties"].update(part.get("properties") or {})
                    merged["required"] += part.get("required") or []
                merged["required"] = sorted(set(merged["required"]))
                if node.get("description"):
                    merged["description"] = node["description"]
                return merged
            reduced = _pick_branch(branches, defs, depth)
            if node.get("description") and "description" not in reduced:
                reduced["description"] = node["description"]
            return reduced

    # --- ordinary node ---------------------------------------------------------
    out = {k: v for k, v in node.items() if k in KEEP_KEYS}
    if "properties" in out:
        out["properties"] = {name: _reduce(sub, defs, depth + 1)
                             for name, sub in (out["properties"] or {}).items()}
    if "items" in out and isinstance(out["items"], dict):
        out["items"] = _reduce(out["items"], defs, depth + 1)
    if isinstance(out.get("type"), list):
        # ["string", "null"] -> "string"; nullability lives in `required`, not in `type`.
        real = [t for t in out["type"] if t != "null"]
        out["type"] = real[0] if real else "string"
    return out


def sanitise_schema(schema: dict) -> dict:
    """Reduce an MCP inputSchema to the subset Ollama's tool parser accepts."""
    if not isinstance(schema, dict):
        raise SchemaError("inputSchema must be an object")
    defs = {}
    for holder in ("$defs", "definitions"):
        defs.update(schema.get(holder) or {})
    reduced = _reduce(schema, defs)
    reduced.setdefault("type", "object")
    reduced.setdefault("properties", {})
    return reduced


def to_ollama_tool(tool, prefix: str = "") -> dict:
    """Convert one MCP tool to an Ollama /api/chat tool definition.

    Accepts either a dict or an SDK Tool object. v2 renamed the attribute to snake_case:
    `tool.inputSchema` raises AttributeError, and `model_dump()` emits `input_schema`, so a
    bridge indexing ["inputSchema"] silently KeyErrors. Both spellings are handled.
    """
    if isinstance(tool, dict):
        name = tool.get("name")
        description = tool.get("description") or tool.get("title") or ""
        schema = tool.get("input_schema") or tool.get("inputSchema") or {}
    else:
        name = getattr(tool, "name", None)
        description = getattr(tool, "description", "") or getattr(tool, "title", "") or ""
        schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
    if not name:
        raise SchemaError("tool has no name")
    return {"type": "function",
            "function": {"name": namespaced(prefix, name),
                         "description": description,
                         "parameters": sanitise_schema(schema)}}


def build_toolset(tools_by_prefix: dict):
    """Convert many servers' tools at once.

    Returns (ollama_tools, routing, skipped). `routing` maps the namespaced name back to
    (prefix, original_name) so a tool call can be dispatched to the right server. A tool
    whose schema cannot be reduced is SKIPPED and reported, never sent malformed - one bad
    schema must not take down every other tool in the prompt.
    """
    ollama_tools, routing, skipped = [], {}, []
    for prefix, tools in tools_by_prefix.items():
        for tool in tools or []:
            try:
                converted = to_ollama_tool(tool, prefix)
            except SchemaError as exc:
                original = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "?")
                skipped.append({"prefix": prefix, "tool": original, "reason": str(exc)})
                continue
            namespaced_name = converted["function"]["name"]
            original = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", "")
            routing[namespaced_name] = (prefix, original)
            ollama_tools.append(converted)
    return ollama_tools, routing, skipped
