"""Hook services and types."""

from nanobot.hooks.base import BaseHook, HookTriggerCallback
from nanobot.hooks.dispatcher import HookDispatchRequest, HookDispatcher, from_rule_event
from nanobot.hooks.manager import HookManager
from nanobot.hooks.mock import MockBtcVolatilityHook
from nanobot.hooks.service import HookService
from nanobot.hooks.types import HookCondition, HookDelivery, HookEvent, HookRule, HookState, HookTarget

__all__ = [
    "BaseHook",
    "HookTriggerCallback",
    "HookDispatchRequest",
    "HookDispatcher",
    "HookManager",
    "MockBtcVolatilityHook",
    "HookService",
    "from_rule_event",
    "HookCondition",
    "HookDelivery",
    "HookEvent",
    "HookRule",
    "HookState",
    "HookTarget",
]
