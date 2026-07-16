"""Operator notification via the existing services/telegram channel (§4)."""
from __future__ import annotations

import anyio


class TelegramNotifier:
    """Thin async wrapper over services.telegram.bot.report (sync httpx)."""

    async def notify(self, text: str) -> None:
        try:
            from services.telegram import bot

            await anyio.to_thread.run_sync(bot.report, text)
        except Exception:
            # Ticket creation must never fail because Telegram is down; the
            # webhook + stored ticket are the durable record.
            pass


class NullNotifier:
    """Collects notifications in memory (tests / notifications disabled)."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def notify(self, text: str) -> None:
        self.sent.append(text)
