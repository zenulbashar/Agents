#!/usr/bin/env python3
"""Filesystem jail for agent tools.

The rules are LOADED from config/access.yaml rather than duplicated here, so the document
and the enforcement cannot drift. access.yaml has described this jail since the repo was
created; until now nothing read it, which made it a written promise that was not true.

Two rules, in this order:
  1. Everything resolves with Path.resolve() BEFORE any check, so a symlink pointing out of
     the tree is caught by the same test as a literal path.
  2. Reads are confined to allow_root; writes are confined to the vault. Even inside those,
     a denylist covers credentials (.env, *.pem, secrets/, .git/config, ~/.ssh).

This is layer one of ADR-007 and it exists because a 4B model emitted `path: "/"` unprompted
on its very first tool call. Argument validation is not the model's job.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml
except ImportError:                                     # pragma: no cover
    raise SystemExit("PyYAML required: pip install pyyaml")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ACCESS = ROOT_DIR / "config" / "access.yaml"

# Denied anywhere, including inside allow_root. Names are matched per path component.
DENY_COMPONENTS = {".ssh", ".aws", ".gnupg", "secrets", ".venv", "node_modules"}
DENY_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt"}
MAX_READ_BYTES = 256 * 1024


class JailError(PermissionError):
    """A tool argument tried to leave the jail. Always report the RESOLVED path."""


def _expand(value) -> Path:
    return Path(os.path.expanduser(str(value))).resolve()


def _is_prose(entry: str) -> bool:
    """access.yaml's deny_always mixes real paths with prose, e.g. '/ (the rest of the Mac)'."""
    return "(" in entry or " " in entry.strip()


def _load():
    cfg = {}
    if ACCESS.exists():
        with ACCESS.open() as fh:
            cfg = yaml.safe_load(fh) or {}
    fs = ((cfg.get("global") or {}).get("filesystem") or {})
    root = _expand(fs.get("allow_root") or ROOT_DIR)
    vault = _expand(fs.get("vault") or (root / "vault"))
    deny = []
    for entry in (fs.get("deny_always") or []):
        text = str(entry).strip()
        if not text or _is_prose(text):
            continue
        deny.append(_expand(text))
    return root, vault, deny


ALLOW_ROOT, VAULT_ROOT, DENY_PATHS = _load()


def _within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _check_denylist(resolved: Path) -> None:
    for denied in DENY_PATHS:
        if _within(resolved, denied):
            raise JailError(f"denied by access.yaml deny_always: {resolved}")
    for part in resolved.parts:
        if part in DENY_COMPONENTS:
            raise JailError(f"denied path component '{part}': {resolved}")
        if part == ".env" or part.startswith(".env."):
            raise JailError(f"denied credential file: {resolved}")
    if resolved.suffix in DENY_SUFFIXES:
        raise JailError(f"denied credential file type '{resolved.suffix}': {resolved}")
    if resolved.name == "config" and resolved.parent.name == ".git":
        raise JailError(f"denied git config (may hold credentials): {resolved}")


def resolve_read(path) -> Path:
    """Resolve a path an agent asked to READ, or raise JailError."""
    if path is None or str(path).strip() == "":
        raise JailError("empty path")
    candidate = Path(os.path.expanduser(str(path)))
    if not candidate.is_absolute():
        candidate = ALLOW_ROOT / candidate
    resolved = candidate.resolve()
    if not _within(resolved, ALLOW_ROOT):
        raise JailError(f"outside the jail {ALLOW_ROOT}: {resolved}")
    _check_denylist(resolved)
    return resolved


def resolve_write(path) -> Path:
    """Resolve a path an agent asked to WRITE. Writes are vault-only.

    Agents draft into the shared brain; they do not edit the code that governs them.
    Widening this is a policy change, not a refactor.
    """
    resolved = resolve_read(path)
    if not _within(resolved, VAULT_ROOT):
        raise JailError(f"writes are restricted to {VAULT_ROOT}: {resolved}")
    if resolved.suffix.lower() not in (".md", ".markdown", ""):
        raise JailError(f"vault writes must be markdown: {resolved}")
    return resolved
