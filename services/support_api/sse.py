"""AI SDK "UI Message Stream v1" SSE encoding (Contract v1 §3).

Every client's reader is turnkey if we emit exactly this shape:
  data: {"type":"start", ...}
  data: {"type":"text-start","id":...} / {"type":"text-delta",...} / {"type":"text-end",...}
  data: {"type":"data-*", "data": ...}       (custom parts)
  data: {"type":"finish"}
  data: [DONE]
Errors mid-stream: {"type":"error","errorText":"..."} then [DONE].
"""
from __future__ import annotations

import json
from typing import Any

STREAM_HEADERS = {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # nginx: never buffer, if one ever fronts us
    "x-vercel-ai-ui-message-stream": "v1",
}

DONE = "data: [DONE]\n\n"


def event(payload: dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n\n"


def start(message_id: str) -> str:
    return event({"type": "start", "messageId": message_id})


def text_start(text_id: str) -> str:
    return event({"type": "text-start", "id": text_id})


def text_delta(text_id: str, delta: str) -> str:
    return event({"type": "text-delta", "id": text_id, "delta": delta})


def text_end(text_id: str) -> str:
    return event({"type": "text-end", "id": text_id})


def data_part(name: str, data: Any) -> str:
    return event({"type": f"data-{name}", "data": data})


def finish() -> str:
    return event({"type": "finish"})


def error(text: str) -> str:
    return event({"type": "error", "errorText": text})
