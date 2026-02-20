"""Mock hook implementation for development and manual testing."""

from __future__ import annotations

import asyncio
from typing import Iterable

from loguru import logger

from nanobot.hooks.base import BaseHook, HookTriggerCallback
from nanobot.hooks.types import HookEvent, HookRule, HookState


class MockBtcVolatilityHook(BaseHook):
    """Emit mock BTC price changes and trigger when threshold is crossed."""

    def __init__(
        self,
        rule: HookRule,
        on_trigger: HookTriggerCallback,
        *,
        interval_s: int = 30,
        values: Iterable[float] | None = None,
    ):
        self.rule = rule
        self.on_trigger = on_trigger
        self.interval_s = interval_s
        self._values = list(values or [100.0, 101.5, 104.2, 102.0, 106.5, 109.0, 104.5])
        self._cursor = 0
        self._state = HookState()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start periodic mock emission."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Mock hook started: {} (every {}s)", self.rule.name, self.interval_s)

    def stop(self) -> None:
        """Stop periodic mock emission."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        """Run periodic ticks until stopped."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Mock hook loop failed ({}): {}", self.rule.id, e)

    async def _tick(self) -> None:
        """Emit one mock value from the configured sequence."""
        if not self._values:
            return
        value = self._values[self._cursor]
        self._cursor = (self._cursor + 1) % len(self._values)
        await self.ingest_value(value)

    async def ingest_value(self, value: float, now_ms: int | None = None) -> HookEvent | None:
        """Ingest one value manually and trigger callback when condition matches."""
        import time

        when_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        prev = self._state.last_value

        if prev is None or prev == 0:
            self._state.last_value = value
            self._state.last_seen_at_ms = when_ms
            return None

        change_pct = ((value - prev) / abs(prev)) * 100.0
        meets_threshold = abs(change_pct) >= self.rule.condition.gte
        cooldown_ok = True
        if self.rule.cooldown_seconds > 0 and self._state.last_trigger_at_ms:
            cooldown_ok = when_ms - self._state.last_trigger_at_ms >= self.rule.cooldown_seconds * 1000

        self._state.last_value = value
        self._state.last_seen_at_ms = when_ms

        if not (meets_threshold and cooldown_ok):
            return None

        event = HookEvent(
            rule_id=self.rule.id,
            source=self.rule.source,
            value=value,
            previous_value=prev,
            change_pct=change_pct,
            rendered_message=self.rule.message_template.format(
                id=self.rule.id,
                name=self.rule.name,
                source=self.rule.source,
                value=value,
                previous_value=prev,
                change_pct=change_pct,
            ),
            payload={"mock": True},
        )
        self._state.last_trigger_at_ms = when_ms
        await self.on_trigger(self.rule, event)
        return event
