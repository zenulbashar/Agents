#!/usr/bin/env python3
"""The agent tool-calling loop.

Before this existed, run_agent() made ONE model call and wrote the reply to data/outbox/ —
agents could talk but not act. This is the loop that lets them act, deliberately small.

Design constraints, each traceable to something measured rather than assumed:

  * num_ctx is set explicitly. Ollama's default here is 4096 and an agent system prompt is
    ~1,876 tokens; on overflow Ollama evicts the oldest NON-system content, which is the tool
    results. The classic symptom is an agent re-calling the same tool forever.
  * think=false. Thinking is on by default and cost 26x the output tokens on short replies.
  * max_iters is enforced in CODE, not in the prompt. A model at ~38% instruction-following
    will not honour a prompt-level cap, and hitting the cap is a DEFECT signal, not a retry.
  * The cap is per tool set, not global: long-horizon decay is domain-stratified — triage-shaped
    work sustains far longer chains than code-writing does (docs/20-autonomy-plan.md §10.1).
  * Every tool argument is validated in Python (services/runtime/jail.py) before execution.

No framework. The one seam every local-model agent framework fails at is parsing a small
model's malformed tool call, and that is precisely the seam we need to own.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

from services.runtime import tools as toolkit

ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_DIR = ROOT / ".claude" / "agents"

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
NUM_CTX = int(os.environ.get("FOUNDRY_NUM_CTX", "16384"))
KEEP_ALIVE = os.environ.get("FOUNDRY_KEEP_ALIVE", "30m")
CALL_TIMEOUT = int(os.environ.get("FOUNDRY_MODEL_TIMEOUT", "600"))
CTX_WARN_RATIO = 0.7

# Iteration caps by shape of work. Code paths get fewer because that is where degradation
# is steepest; read/triage paths sustain longer chains.
MAX_ITERS_DEFAULT = 6
MAX_ITERS_TRIAGE = 8
MAX_ITERS_CODE = 4

# Claude Code frontmatter tool names -> local tools. Bash maps to run_check (a fixed menu),
# NOT to a shell. Edit maps to nothing: agents draft into the vault, they do not edit the
# code that governs them. WebSearch/WebFetch map to nothing: egress stays loopback-only.
GRANT_MAP = {
    "Read": "read_file",
    "Grep": "grep",
    "Glob": "list_files",
    "Write": "write_note",
    "Bash": "run_check",
}


def _noop_log(agent, event, detail):
    pass


def post_json(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never proxy localhost
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tools_for_agent(agent_key: str):
    """Translate the generated frontmatter grant into local tool names.

    The frontmatter is a Claude Code artefact describing a different runtime. We honour its
    INTENT (who may write, who may run checks) while refusing its `Bash` grant, which 19 of
    59 agents carry and none of them should have here.
    """
    path = AGENT_DIR / (re.sub(r"[^A-Za-z0-9_-]", "", agent_key) + ".md")
    if not path.exists():
        return list(toolkit.READ_ONLY)
    match = re.search(r"^tools:\s*(.+)$", path.read_text(), re.MULTILINE)
    if not match:
        return list(toolkit.READ_ONLY)
    granted = []
    for raw in match.group(1).split(","):
        local = GRANT_MAP.get(raw.strip())
        if local and local not in granted:
            granted.append(local)
    return granted or list(toolkit.READ_ONLY)


def cap_for(tool_names) -> int:
    if "run_check" in tool_names:
        return MAX_ITERS_CODE
    if "write_note" in tool_names:
        return MAX_ITERS_DEFAULT
    return MAX_ITERS_TRIAGE


def _call(model, messages, schemas):
    body = {"model": model, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
            "options": {"num_ctx": NUM_CTX}, "messages": messages}
    if schemas:
        body["tools"] = schemas
    return post_json(OLLAMA + "/api/chat", body, CALL_TIMEOUT)


def run(agent_key, system, task, model, tool_names=None, max_iters=None,
        budget_s=600, log=_noop_log):
    """Run one agent task to completion or to a cap. Never raises."""
    tool_names = tool_names if tool_names is not None else tools_for_agent(agent_key)
    max_iters = max_iters or cap_for(tool_names)
    schemas = toolkit.schemas(tool_names)

    messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
    started = time.time()
    calls, failures, iterations = [], 0, 0

    for iterations in range(1, max_iters + 1):
        if time.time() - started > budget_s:
            log(agent_key, "executor-budget", {"seconds": round(time.time() - started, 1)})
            return {"status": "budget", "output": "", "iterations": iterations - 1,
                    "tool_calls": calls, "hit_cap": False}
        try:
            data = _call(model, messages, schemas)
        except Exception as exc:
            log(agent_key, "executor-error", {"error": str(exc), "iteration": iterations})
            return {"status": "error", "output": "", "reason": str(exc),
                    "iterations": iterations - 1, "tool_calls": calls, "hit_cap": False}

        used = int(data.get("prompt_eval_count") or 0)
        if used > CTX_WARN_RATIO * NUM_CTX:
            log(agent_key, "context-pressure",
                {"prompt_tokens": used, "num_ctx": NUM_CTX, "iteration": iterations,
                 "note": "older non-system content is being evicted - tool results are at risk"})

        message = data.get("message") or {}
        requested = message.get("tool_calls") or []
        messages.append(message)

        if not requested:
            output = (message.get("content") or "").strip()
            log(agent_key, "executor-done",
                {"iterations": iterations, "tool_calls": len(calls), "tool_failures": failures,
                 "seconds": round(time.time() - started, 1), "chars": len(output)})
            return {"status": "done", "output": output, "iterations": iterations,
                    "tool_calls": calls, "hit_cap": False}

        for call in requested:
            fn = (call.get("function") or {})
            name = fn.get("name") or "?"
            args = fn.get("arguments")
            if isinstance(args, str):                    # some models emit JSON as a string
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            result, ok = toolkit.execute(name, args or {})
            failures += 0 if ok else 1
            calls.append({"tool": name, "args": args, "ok": ok})
            log(agent_key, "tool-call", {"tool": name, "args": args, "ok": ok,
                                         "iteration": iterations,
                                         "result": result[:200]})
            messages.append({"role": "tool", "content": result})

    # Reaching the cap means the model never stopped asking for tools. That is a defect to
    # investigate - a loop, or context overflow eating the results - not something to retry.
    log(agent_key, "executor-cap",
        {"max_iters": max_iters, "tool_calls": len(calls), "tool_failures": failures,
         "seconds": round(time.time() - started, 1),
         "note": "hit the iteration cap - treat as a defect, do not simply retry"})
    return {"status": "cap", "output": "", "iterations": max_iters,
            "tool_calls": calls, "hit_cap": True}
