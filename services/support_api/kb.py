"""Per-app knowledge base -> Anthropic document blocks with citations.

KB layout on disk (curated by the operator, versioned in git):
    <kb_dir>/common/*.md        loaded for every department
    <kb_dir>/<department>/*.md  department-specific

Optional YAML front matter per file:
    ---
    title: Refunds policy
    url: https://app.example.com/help/refunds
    ---

Documents go into the FIRST user turn as `document` blocks with
citations enabled, and the last block carries cache_control so the whole
static prefix (system prompt + KB) is a cached prompt prefix (§1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class KBDoc:
    title: str
    url: str | None
    text: str

    def source_ref(self) -> dict[str, Any]:
        ref: dict[str, Any] = {"title": self.title}
        if self.url:
            ref["url"] = self.url
        return ref


def _parse(path: Path) -> KBDoc:
    raw = path.read_text(encoding="utf-8")
    title = path.stem.replace("-", " ").replace("_", " ").strip().title()
    url = None
    match = _FRONT_MATTER.match(raw)
    if match:
        raw = raw[match.end():]
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip().strip("'\"")
            if key == "title" and value:
                title = value
            elif key == "url" and value:
                url = value
    return KBDoc(title=title, url=url, text=raw.strip())


def load_kb(kb_dir: Path, department: str, max_docs: int = 25) -> list[KBDoc]:
    docs: list[KBDoc] = []
    for sub in ("common", department):
        folder = kb_dir / sub
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            docs.append(_parse(path))
    return docs[:max_docs]


def document_blocks(docs: list[KBDoc], *, plain: bool = False) -> list[dict[str, Any]]:
    """Anthropic content blocks for the KB, citations enabled, cached prefix.

    `plain=True` is the degraded form used when the endpoint is Ollama's
    Anthropic-compatible shim, which rejects document blocks outright:
        400 invalid_request_error - cannot unmarshal object into Go struct field
        MessagesRequest.messages.citations of type []anthropic.Citation
    The shim models `citations` as an array; the real API sends {"enabled": true}.

    What is lost is real and should not be glossed: the answer is still grounded in
    the same KB text, but the model no longer emits citation deltas, so `sources` on
    a reply become empty rather than model-attested. Grounding survives; provenance
    does not. See docs/20-autonomy-plan.md ADR-005.
    """
    if plain:
        return [{"type": "text",
                 "text": f"<kb_document title=\"{doc.title}\">\n{doc.text}\n</kb_document>"}
                for doc in docs]
    blocks: list[dict[str, Any]] = []
    for doc in docs:
        block: dict[str, Any] = {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": doc.text},
            "title": doc.title,
            "citations": {"enabled": True},
        }
        if doc.url:
            block["context"] = f"Source URL: {doc.url}"
        blocks.append(block)
    if blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks
