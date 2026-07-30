#!/usr/bin/env python3
"""Retrieval over the vault and docs. Markdown is the source of truth; the index is derived.

ADR-004. No vector database, and the arithmetic is why: the corpus is 35 markdown files and
~42,000 words - roughly 130 chunks, about 0.4MB of float32. Qdrant's own capacity formula
sizes the whole thing at single-digit megabytes. Running a database server to hold that,
beside a 3.5GB resident model on a 16GB box, is indefensible. Brute-force cosine over a
numpy array is sub-millisecond at this scale and stays under 5ms at 100x growth.

Keyword search (SQLite FTS5, stdlib) and semantic search (nomic-embed-text, already on disk)
are fused with Reciprocal Rank Fusion. Keyword is deliberately first: with a corpus this
small, a model handed three ripgrep results beats a badly-tuned retrieval stack, and a wrong
answer is debuggable with `rg` instead of by inspecting embeddings.

The index is disposable. If it is corrupt, delete data/memory and rebuild - markdown is the
only thing that matters, which is the point of keeping it as the source of truth.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_DIR = ROOT / "data" / "memory"
DB_PATH = INDEX_DIR / "index.sqlite"
VEC_PATH = INDEX_DIR / "vectors.npy"

SOURCES = ["vault", "docs"]
EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text:latest")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
TARGET_WORDS = 250          # ~340 tokens; comfortably inside nomic's 8192 window
EMBED_BATCH = 32
RRF_K = 60                  # standard Reciprocal Rank Fusion constant


def _post(path, payload, timeout=300):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def embed(texts):
    """Embed a list of strings. Returns an (n, dim) float32 array, L2-normalised."""
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        data = _post("/api/embed", {"model": EMBED_MODEL, "input": batch})
        out.extend(data.get("embeddings") or [])
    arr = np.asarray(out, dtype=np.float32)
    if arr.size == 0:
        return arr
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return arr / np.clip(norms, 1e-8, None)      # normalise once, so cosine is a dot product


def chunk_markdown(text: str):
    """Split on blank lines, accumulating to ~TARGET_WORDS, carrying the nearest heading.

    The heading is prepended to every chunk because a chunk that says "it must be approved
    by the operator" is useless without knowing what "it" is.
    """
    heading = ""
    chunks, buf, count = [], [], 0
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            heading = block.lstrip("#").strip()
        words = len(block.split())
        if count + words > TARGET_WORDS and buf:
            chunks.append(("\n\n".join(buf), heading))
            buf, count = [], 0
        buf.append(block)
        count += words
    if buf:
        chunks.append(("\n\n".join(buf), heading))
    return chunks


def _connect():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks "
                "USING fts5(path, heading, body, tokenize='porter unicode61')")
    return con


def build(verbose=False):
    """Rebuild the index from scratch. Cheap enough that incremental updates are not worth it."""
    files = sorted(p for src in SOURCES for p in (ROOT / src).rglob("*.md"))
    rows = []
    for path in files:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for body, heading in chunk_markdown(text):
            rows.append((str(path.relative_to(ROOT)), heading, body))

    con = _connect()
    con.execute("DELETE FROM chunks")
    con.executemany("INSERT INTO chunks(path, heading, body) VALUES (?, ?, ?)", rows)
    con.commit()
    con.close()

    vectors = embed([f"{h}\n{b}" if h else b for _, h, b in rows]) if rows else np.zeros((0, 768), np.float32)
    np.save(VEC_PATH, vectors)
    if verbose:
        size = VEC_PATH.stat().st_size / 1024
        print(f"indexed {len(rows)} chunks from {len(files)} files "
              f"({size:.0f}KB of vectors, dim={vectors.shape[1] if len(vectors) else 0})")
    return len(rows)


def _fts_query(text: str) -> str:
    """FTS5 has its own query syntax; user text must be sanitised or it raises."""
    terms = re.findall(r"[A-Za-z0-9_]+", text)
    return " OR ".join(f'"{t}"' for t in terms) if terms else '""'


def search(query: str, k: int = 6):
    """Hybrid keyword + semantic search. Returns [{path, heading, body, score}]."""
    if not DB_PATH.exists() or not VEC_PATH.exists():
        return []
    con = _connect()
    rows = con.execute("SELECT rowid, path, heading, body FROM chunks").fetchall()
    by_rowid = {r[0]: r for r in rows}

    ranks: dict[int, float] = {}
    try:
        hits = con.execute(
            "SELECT rowid FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
            (_fts_query(query), k * 3)).fetchall()
        for position, (rowid,) in enumerate(hits):
            ranks[rowid] = ranks.get(rowid, 0.0) + 1.0 / (RRF_K + position + 1)
    except sqlite3.OperationalError:
        pass                                        # a malformed FTS query must not kill search
    con.close()

    vectors = np.load(VEC_PATH)
    if len(vectors) and len(rows):
        qv = embed([query])
        if qv.size:
            sims = vectors @ qv[0]
            order = np.argsort(-sims)[:k * 3]
            ordered_rowids = [r[0] for r in rows]
            for position, idx in enumerate(order):
                if idx < len(ordered_rowids):
                    rowid = ordered_rowids[idx]
                    ranks[rowid] = ranks.get(rowid, 0.0) + 1.0 / (RRF_K + position + 1)

    best = sorted(ranks.items(), key=lambda kv: -kv[1])[:k]
    results = []
    for rowid, score in best:
        row = by_rowid.get(rowid)
        if row:
            results.append({"path": row[1], "heading": row[2], "body": row[3], "score": round(score, 5)})
    return results


if __name__ == "__main__":
    build(verbose=True)
