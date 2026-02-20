"""Hook service for source-driven trigger rules."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot.hooks.types import HookCondition, HookDelivery, HookEvent, HookRule, HookState, HookTarget


def _now_ms() -> int:
    return int(time.time() * 1000)


class HookService:
    """Manage hook rules, evaluate source updates, and dispatch events."""

    def __init__(
        self,
        rules_path: Path,
        state_path: Path,
        on_trigger: Callable[[HookRule, HookEvent], Awaitable[str | None]] | None = None,
    ):
        self.rules_path = rules_path
        self.state_path = state_path
        self.on_trigger = on_trigger
        self._rules: list[HookRule] | None = None
        self._state: dict[str, HookState] | None = None

    def _load_rules(self) -> list[HookRule]:
        if self._rules is not None:
            return self._rules
        if not self.rules_path.exists():
            self._rules = []
            return self._rules
        try:
            raw = json.loads(self.rules_path.read_text(encoding="utf-8"))
            out: list[HookRule] = []
            for item in raw.get("rules", []):
                condition_obj = item.get("condition", {})
                target_obj = item.get("target", {})
                delivery_obj = item.get("delivery", {})
                out.append(
                    HookRule(
                        id=item["id"],
                        name=item.get("name", item["id"]),
                        source=item.get("source", ""),
                        enabled=item.get("enabled", True),
                        condition=HookCondition(
                            kind=condition_obj.get("kind", "pct_change"),
                            gte=float(condition_obj.get("gte", 0.0)),
                        ),
                        target=HookTarget(
                            kind=target_obj.get("kind", "root"),
                            expert=target_obj.get("expert"),
                        ),
                        delivery=HookDelivery(
                            channel=delivery_obj.get("channel", "cli"),
                            chat_id=delivery_obj.get("chat_id", "direct"),
                            deliver_result=delivery_obj.get("deliver_result", True),
                        ),
                        message_template=item.get(
                            "message_template",
                            "[Hook: {name}] {source} changed {change_pct:.2f}% (value={value})",
                        ),
                        cooldown_seconds=int(item.get("cooldown_seconds", 0)),
                        metadata=item.get("metadata", {}) or {},
                    )
                )
            self._rules = out
        except Exception as e:
            logger.warning("Failed to load hook rules: {}", e)
            self._rules = []
        return self._rules

    def _save_rules(self) -> None:
        rules = self._load_rules()
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "source": r.source,
                    "enabled": r.enabled,
                    "condition": {"kind": r.condition.kind, "gte": r.condition.gte},
                    "target": {"kind": r.target.kind, "expert": r.target.expert},
                    "delivery": {
                        "channel": r.delivery.channel,
                        "chat_id": r.delivery.chat_id,
                        "deliver_result": r.delivery.deliver_result,
                    },
                    "message_template": r.message_template,
                    "cooldown_seconds": r.cooldown_seconds,
                    "metadata": r.metadata,
                }
                for r in rules
            ],
        }
        self.rules_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_state(self) -> dict[str, HookState]:
        if self._state is not None:
            return self._state
        if not self.state_path.exists():
            self._state = {}
            return self._state
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            state: dict[str, HookState] = {}
            for rid, item in (raw.get("rules", {}) or {}).items():
                state[rid] = HookState(
                    last_value=item.get("last_value"),
                    last_seen_at_ms=item.get("last_seen_at_ms"),
                    last_trigger_at_ms=item.get("last_trigger_at_ms"),
                )
            self._state = state
        except Exception as e:
            logger.warning("Failed to load hook state: {}", e)
            self._state = {}
        return self._state

    def _save_state(self) -> None:
        state = self._load_state()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "rules": {
                rid: {
                    "last_value": st.last_value,
                    "last_seen_at_ms": st.last_seen_at_ms,
                    "last_trigger_at_ms": st.last_trigger_at_ms,
                }
                for rid, st in state.items()
            },
        }
        self.state_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _validate_rule(rule: HookRule) -> None:
        if not rule.source:
            raise ValueError("source is required")
        if rule.condition.kind != "pct_change":
            raise ValueError(f"unsupported condition kind '{rule.condition.kind}'")
        if rule.condition.gte <= 0:
            raise ValueError("condition.gte must be > 0")
        if rule.target.kind == "expert" and not rule.target.expert:
            raise ValueError("target.expert is required when target.kind=expert")
        if not rule.delivery.channel or not rule.delivery.chat_id:
            raise ValueError("delivery.channel and delivery.chat_id are required")

    def list_rules(self, include_disabled: bool = False) -> list[HookRule]:
        """List hook rules."""
        rules = self._load_rules()
        if include_disabled:
            return list(rules)
        return [r for r in rules if r.enabled]

    def add_rule(
        self,
        *,
        name: str,
        source: str,
        gte_pct: float,
        target_kind: str = "root",
        target_expert: str | None = None,
        channel: str = "cli",
        chat_id: str = "direct",
        message_template: str | None = None,
        cooldown_seconds: int = 0,
        deliver_result: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> HookRule:
        """Create and persist a new hook rule."""
        rule = HookRule(
            id=str(uuid.uuid4())[:8],
            name=name,
            source=source,
            condition=HookCondition(kind="pct_change", gte=float(gte_pct)),
            target=HookTarget(kind=target_kind, expert=target_expert),
            delivery=HookDelivery(channel=channel, chat_id=chat_id, deliver_result=deliver_result),
            message_template=message_template
            or "[Hook: {name}] {source} changed {change_pct:.2f}% (from {previous_value} to {value})",
            cooldown_seconds=max(0, int(cooldown_seconds)),
            metadata=metadata or {},
        )
        self._validate_rule(rule)

        rules = self._load_rules()
        rules.append(rule)
        self._save_rules()
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by id."""
        rules = self._load_rules()
        before = len(rules)
        self._rules = [r for r in rules if r.id != rule_id]
        if len(self._rules) == before:
            return False
        self._save_rules()
        state = self._load_state()
        state.pop(rule_id, None)
        self._save_state()
        return True

    def enable_rule(self, rule_id: str, enabled: bool = True) -> HookRule | None:
        """Enable or disable a rule."""
        for rule in self._load_rules():
            if rule.id == rule_id:
                rule.enabled = enabled
                self._save_rules()
                return rule
        return None

    async def process_value(
        self,
        *,
        source: str,
        value: float,
        payload: dict[str, Any] | None = None,
        now_ms: int | None = None,
    ) -> list[HookEvent]:
        """Process a source value and trigger matching rules."""
        when_ms = now_ms if now_ms is not None else _now_ms()
        extra = payload or {}
        state = self._load_state()
        rules = [r for r in self._load_rules() if r.enabled and r.source == source]
        events: list[HookEvent] = []

        for rule in rules:
            st = state.get(rule.id, HookState())
            prev = st.last_value
            change_pct: float | None = None

            if prev is None or prev == 0:
                st.last_value = value
                st.last_seen_at_ms = when_ms
                state[rule.id] = st
                continue

            change_pct = ((value - prev) / abs(prev)) * 100.0
            meets_threshold = abs(change_pct) >= rule.condition.gte
            cooldown_ok = True
            if rule.cooldown_seconds > 0 and st.last_trigger_at_ms:
                cooldown_ok = when_ms - st.last_trigger_at_ms >= rule.cooldown_seconds * 1000

            if meets_threshold and cooldown_ok:
                template_vars = {
                    "id": rule.id,
                    "name": rule.name,
                    "source": source,
                    "value": value,
                    "previous_value": prev,
                    "change_pct": change_pct,
                    **extra,
                }
                try:
                    rendered = rule.message_template.format(**template_vars)
                except Exception:
                    rendered = (
                        f"[Hook: {rule.name}] {source} changed {change_pct:.2f}% "
                        f"(from {prev} to {value})"
                    )
                event = HookEvent(
                    rule_id=rule.id,
                    source=source,
                    value=value,
                    previous_value=prev,
                    change_pct=change_pct,
                    rendered_message=rendered,
                    payload=extra,
                )
                events.append(event)
                st.last_trigger_at_ms = when_ms

                if self.on_trigger:
                    try:
                        await self.on_trigger(rule, event)
                    except Exception as e:
                        logger.error("Hook trigger callback failed for {}: {}", rule.id, e)

            st.last_value = value
            st.last_seen_at_ms = when_ms
            state[rule.id] = st

        self._save_state()
        return events

