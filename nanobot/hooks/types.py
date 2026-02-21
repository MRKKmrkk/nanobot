"""Hook types."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class HookCondition:
    """Condition definition for a hook rule."""

    kind: Literal["pct_change"] = "pct_change"
    gte: float = 0.0


@dataclass
class HookTarget:
    """Target destination for a triggered hook."""

    kind: Literal["root", "expert"] = "root"
    expert: str | None = None


@dataclass
class HookDelivery:
    """Delivery metadata for hook-triggered messages."""

    channel: str = "cli"
    chat_id: str = "direct"
    deliver_result: bool = True


@dataclass
class HookRule:
    """A hook rule that can be evaluated against source values."""

    id: str
    name: str
    source: str
    enabled: bool = True
    condition: HookCondition = field(default_factory=HookCondition)
    target: HookTarget = field(default_factory=HookTarget)
    delivery: HookDelivery = field(default_factory=HookDelivery)
    message_template: str = "[Hook: {name}] {source} changed {change_pct:.2f}% (value={value})"
    cooldown_seconds: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookState:
    """Per-rule runtime state used for change detection and cooldown."""

    last_value: float | None = None
    last_seen_at_ms: int | None = None
    last_trigger_at_ms: int | None = None


@dataclass
class HookEvent:
    """A single triggered hook event."""

    rule_id: str
    source: str
    value: float
    previous_value: float | None
    change_pct: float | None
    rendered_message: str
    payload: dict[str, Any] = field(default_factory=dict)

