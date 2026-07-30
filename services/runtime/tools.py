#!/usr/bin/env python3
"""The tool set agents actually get.

Five tools, read-first. Deliberately NOT here: a general `Bash`. The generated agent
frontmatter grants `Bash` to 19 of 59 agents, but that frontmatter is a Claude Code artefact
and must not survive into the local executor — a 4B model at ~38% instruction-following does
not get an arbitrary shell. `run_check` is the replacement: a fixed menu, no free text.

Every argument is validated in Python before anything executes. Grammar-constrained decoding
guarantees the SHAPE of a tool call, never the VALUES, so the jail is the only real control.
"""
from __future__ import annotations

import re
import time
import subprocess
from pathlib import Path

from services.runtime import jail

MAX_MATCHES = 60
MAX_LIST = 200
MAX_OUTPUT_CHARS = 8000
CHECK_TIMEOUT = 180

# The complete set of commands an agent may cause to run. No shell, no interpolation:
# the model picks a NAME, never an argv. Adding an entry is a deliberate act.
CHECKS = {
    "tests":      ["pytest", "-q"],
    "lint":       ["ruff", "check", "."],
    "validate":   ["make", "validate"],
    "agents":     ["make", "agents"],
    "git-status": ["git", "status", "--porcelain"],
    "git-diff":   ["git", "diff", "--stat"],
}

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "data", "logs", "workspaces"}


class ToolError(Exception):
    """A tool refused its arguments. The message goes back to the model verbatim so it can retry."""


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n[clipped at {MAX_OUTPUT_CHARS} chars]"


def _require_str(args: dict, key: str, required: bool = True, default: str = "") -> str:
    value = args.get(key, default if not required else None)
    if value is None:
        raise ToolError(f"missing required argument '{key}'")
    if not isinstance(value, str):
        raise ToolError(f"argument '{key}' must be a string, got {type(value).__name__}")
    return value


# --------------------------------------------------------------------------- tools
def read_file(args: dict) -> str:
    path = jail.resolve_read(_require_str(args, "path"))
    if not path.is_file():
        raise ToolError(f"not a file: {path}")
    if path.stat().st_size > jail.MAX_READ_BYTES:
        raise ToolError(f"file too large ({path.stat().st_size} bytes); use grep instead")
    try:
        return _clip(path.read_text(errors="replace"))
    except OSError as exc:
        raise ToolError(f"could not read: {exc}")


def list_files(args: dict) -> str:
    path = jail.resolve_read(_require_str(args, "path", required=False, default="."))
    if not path.is_dir():
        raise ToolError(f"not a directory: {path}")
    names = []
    for child in sorted(path.iterdir()):
        if child.name in SKIP_DIRS or child.name.startswith("."):
            continue
        names.append(child.name + ("/" if child.is_dir() else ""))
        if len(names) >= MAX_LIST:
            names.append(f"[... truncated at {MAX_LIST} entries]")
            break
    return "\n".join(names) or "(empty)"


def grep(args: dict) -> str:
    pattern = _require_str(args, "pattern")
    root = jail.resolve_read(_require_str(args, "path", required=False, default="."))
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        raise ToolError(f"invalid regular expression: {exc}")

    targets = [root] if root.is_file() else [
        p for p in root.rglob("*")
        if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)
    ]
    hits = []
    for target in targets:
        try:
            for num, line in enumerate(target.read_text(errors="replace").splitlines(), 1):
                if rx.search(line):
                    rel = target.relative_to(jail.ALLOW_ROOT)
                    hits.append(f"{rel}:{num}: {line.strip()[:200]}")
                    if len(hits) >= MAX_MATCHES:
                        hits.append(f"[... truncated at {MAX_MATCHES} matches]")
                        return "\n".join(hits)
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(hits) or "(no matches)"


def write_note(args: dict) -> str:
    """Write a vault note, stamped with machine-generated provenance.

    The stamp exists because of an observed failure, not a hypothetical one. Asked to edit
    config/policies.yaml, an agent was correctly blocked by the jail - and then wrote a note
    asserting "File modified: config/policies.yaml. Set merge_to_main to auto". The file was
    never touched. Containment held; the agent's ACCOUNT of what happened was fabricated.

    A note is a draft by an agent that cannot verify its own claims. The reader has to be told
    that in text the model does not author and cannot suppress.
    """
    path = jail.resolve_write(_require_str(args, "path"))
    content = _require_str(args, "content")
    stamp = ("\n\n---\n"
             f"*Drafted by an agent at {time.strftime('%Y-%m-%dT%H:%M:%S%z')}. "
             "Unverified: an agent cannot change anything outside this vault, so any claim "
             "here that a file, config, or system was modified is a claim about intent, not "
             "a record of fact. The activity log is the record.*\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + stamp)
    return f"wrote {len(content)} chars to {path.relative_to(jail.ALLOW_ROOT)} (provenance stamp appended)"


def search_memory(args: dict) -> str:
    """Hybrid keyword+semantic search over the vault and docs (ADR-004).

    Returned to the model as path + heading + body so it can cite where an answer came
    from. An agent that answers from this without a path is answering from memory.
    """
    from services.runtime import memory

    query = _require_str(args, "query")
    try:
        hits = memory.search(query, k=int(args.get("k") or 5))
    except Exception as exc:
        raise ToolError(f"memory search failed ({exc}); run `make index` to build it")
    if not hits:
        return "(no matches - the index may not be built; run `make index`)"
    return _clip("\n\n".join(
        f"[{h['path']}] {h['heading']}\n{h['body']}" for h in hits))


def run_check(args: dict) -> str:
    name = _require_str(args, "name")
    if name not in CHECKS:
        raise ToolError(f"unknown check '{name}'. Allowed: {', '.join(sorted(CHECKS))}")
    try:
        proc = subprocess.run(CHECKS[name], cwd=str(jail.ALLOW_ROOT), capture_output=True,
                              text=True, timeout=CHECK_TIMEOUT, shell=False)
    except subprocess.TimeoutExpired:
        raise ToolError(f"check '{name}' timed out after {CHECK_TIMEOUT}s")
    except FileNotFoundError:
        raise ToolError(f"check '{name}' is not installed on this host")
    return _clip(f"exit={proc.returncode}\n{proc.stdout}{proc.stderr}")


# --------------------------------------------------------------------------- registry
SPECS = [
    {"name": "read_file", "handler": read_file,
     "description": "Read a UTF-8 text file inside the Foundry tree. Paths are relative to the repo root.",
     "schema": {"type": "object", "required": ["path"],
                "properties": {"path": {"type": "string", "description": "e.g. config/policies.yaml"}}}},
    {"name": "list_files", "handler": list_files,
     "description": "List the entries of a directory inside the Foundry tree.",
     "schema": {"type": "object",
                "properties": {"path": {"type": "string", "description": "directory, defaults to the repo root"}}}},
    {"name": "grep", "handler": grep,
     "description": "Search file contents by regular expression and return file:line matches.",
     "schema": {"type": "object", "required": ["pattern"],
                "properties": {"pattern": {"type": "string", "description": "a Python regular expression"},
                               "path": {"type": "string", "description": "file or directory to search"}}}},
    {"name": "write_note", "handler": write_note,
     "description": "Write a markdown note into the shared vault. This is the ONLY way to persist work.",
     "schema": {"type": "object", "required": ["path", "content"],
                "properties": {"path": {"type": "string", "description": "e.g. vault/00-inbox/note.md"},
                               "content": {"type": "string"}}}},
    {"name": "search_memory", "handler": search_memory,
     "description": "Search the shared vault and docs for relevant passages. Prefer this over "
                    "guessing: it returns the file path so you can cite where an answer came from.",
     "schema": {"type": "object", "required": ["query"],
                "properties": {"query": {"type": "string", "description": "what you are looking for"},
                               "k": {"type": "integer", "description": "how many passages, default 5"}}}},
    {"name": "run_check", "handler": run_check,
     "description": "Run one named, pre-approved check. You cannot run arbitrary commands.",
     "schema": {"type": "object", "required": ["name"],
                "properties": {"name": {"type": "string", "enum": sorted(CHECKS)}}}},
]

BY_NAME = {spec["name"]: spec for spec in SPECS}
READ_ONLY = ["read_file", "list_files", "grep", "search_memory"]


def schemas(names=None):
    """Ollama /api/chat tool schemas for the named tools (all read-first tools by default)."""
    chosen = names or [s["name"] for s in SPECS]
    return [{"type": "function",
             "function": {"name": s["name"], "description": s["description"],
                          "parameters": s["schema"]}}
            for s in SPECS if s["name"] in chosen]


def execute(name: str, args: dict) -> tuple[str, bool]:
    """Run a tool. Returns (result_text, ok). Never raises: the model needs to see the error."""
    spec = BY_NAME.get(name)
    if spec is None:
        return f"ERROR: no such tool '{name}'. Available: {', '.join(sorted(BY_NAME))}", False
    if not isinstance(args, dict):
        return f"ERROR: arguments for '{name}' must be an object", False
    try:
        return spec["handler"](args), True
    except (ToolError, jail.JailError) as exc:
        return f"ERROR: {exc}", False
    except Exception as exc:                                # never kill the loop on a tool bug
        return f"ERROR: {type(exc).__name__}: {exc}", False
