"""Base abstractions for code-defined hooks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from nanobot.hooks.types import HookEvent, HookRule


HookTriggerCallback = Callable[[HookRule, HookEvent], Awaitable[str | None]]


class BaseHook(ABC):
    """Abstract base class for hook implementations."""

    @abstractmethod
    async def start(self) -> None:
        """Start hook processing."""

    @abstractmethod
    def stop(self) -> None:
        """Stop hook processing."""

