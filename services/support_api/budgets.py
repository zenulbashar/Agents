"""Cost ceilings + per-subject rate limiting (Contract v1 §6).

Token budgets are enforced from durable usage rows per (app_id, tenant_id):
one per conversation, one per UTC day. The subject rate limit is a cheap
in-process sliding window layered on top of the client app's own limit.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from .models import AuthContext
from .settings import Settings
from .store import Store


class BudgetExceeded(Exception):
    def __init__(self, scope: str) -> None:
        super().__init__(f"token budget exceeded: {scope}")
        self.scope = scope


class RateLimited(Exception):
    pass


class SubjectRateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)

    def check(self, ctx: AuthContext) -> None:
        now = time.monotonic()
        window = self._hits[(ctx.app_id, ctx.tenant_id, ctx.subject.id)]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.per_minute:
            raise RateLimited()
        window.append(now)


async def check_budgets(
    store: Store, settings: Settings, ctx: AuthContext, conversation_id: str | None
) -> None:
    if await store.usage_today(ctx.app_id, ctx.tenant_id) >= settings.daily_token_budget:
        raise BudgetExceeded("daily")
    if conversation_id is not None:
        used = await store.usage_conversation(ctx.app_id, ctx.tenant_id, conversation_id)
        if used >= settings.conversation_token_budget:
            raise BudgetExceeded("conversation")
