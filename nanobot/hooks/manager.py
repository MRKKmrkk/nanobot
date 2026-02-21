"""Hook manager for lifecycle control of hook implementations."""

from __future__ import annotations

from nanobot.hooks.base import BaseHook


class HookManager:
    """Manage start/stop lifecycle of registered hooks."""

    def __init__(self, hooks: list[BaseHook] | None = None):
        self.hooks = hooks or []

    async def start(self) -> None:
        """Start all hooks."""
        for hook in self.hooks:
            await hook.start()

    def stop(self) -> None:
        """Stop all hooks."""
        for hook in self.hooks:
            hook.stop()

