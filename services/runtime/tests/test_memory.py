"""Unit tests for the retrieval index's pure parts.

Search quality is not unit-testable and is not tested here - that is what the eval set is
for. What IS tested is the machinery that silently corrupts retrieval when it breaks:
chunking that drops headings, and FTS5 query construction, which raises on unescaped user
text and would otherwise take the whole search down on a question containing a quote mark.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.runtime import memory                       # noqa: E402


def test_chunking_carries_the_nearest_heading():
    """A chunk saying 'it must be approved by the operator' is useless without the heading."""
    text = "# Bright lines\n\nMerging to main is gated.\n\n## Secrets\n\nReading one is a gate."
    chunks = memory.chunk_markdown(text)
    headings = [h for _, h in chunks]
    assert any("Bright lines" in h or "Secrets" in h for h in headings)


def test_chunking_splits_long_documents():
    text = "\n\n".join("word " * 120 for _ in range(6))     # ~720 words, target is 250
    assert len(memory.chunk_markdown(text)) > 1


def test_chunking_keeps_short_documents_whole():
    assert len(memory.chunk_markdown("# T\n\nshort body")) == 1


def test_empty_document_produces_no_chunks():
    assert memory.chunk_markdown("   \n\n  \n") == []


def test_fts_query_escapes_text_that_would_raise():
    """FTS5 has its own syntax; raw user text is a query error, not a no-match."""
    for raw in ['what are the "bright lines"?', "NOT AND OR", "a-b c*d", "'quoted'", "()"]:
        built = memory._fts_query(raw)
        assert '"' in built or built == '""'
        assert "(" not in built and ")" not in built


def test_fts_query_on_empty_input_is_still_valid():
    assert memory._fts_query("!!!") == '""'


def test_embed_returns_unit_vectors():
    """Cosine similarity is computed as a plain dot product, which is only correct if the
    vectors are normalised at index time. If this regresses, ranking silently degrades."""
    import numpy as np

    vectors = memory.embed(["alpha beta", "gamma delta"])
    if vectors.size == 0:                                   # Ollama not running: skip, do not fail
        return
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3), norms
