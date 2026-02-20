"""Hook extension implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nanobot.extensions.base import GatewayExtensionContext, NanobotExtension
from nanobot.hooks.dispatcher import HookDispatcher, from_rule_event
from nanobot.hooks.manager import HookManager
from nanobot.hooks.mock import MockBtcVolatilityHook
from nanobot.hooks.types import HookCondition, HookDelivery, HookEvent, HookRule, HookTarget

async def dispatch_hook_event(agent: Any, bus: Any, rule: HookRule, event: HookEvent) -> str | None:
    """Route one hook event to root/expert and optionally deliver result."""
    dispatcher = HookDispatcher(agent=agent, bus=bus)
    return await dispatcher.dispatch(from_rule_event(rule, event))


class HookExtension(NanobotExtension):
    """Load and run configured hooks."""

    extension_id = "hook"

    def __init__(self):
        self._hooks = HookManager([])
        self._trigger_count = 0
        self._last_trigger_at: datetime | None = None
        self._last_error: str | None = None

    def configure(self, context: GatewayExtensionContext) -> None:
        async def on_hook_trigger(rule: HookRule, event: HookEvent) -> str | None:
            self._last_trigger_at = datetime.now(timezone.utc)
            self._trigger_count += 1
            try:
                result = await dispatch_hook_event(context.agent, context.bus, rule, event)
                self._last_error = None
                return result
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"
                raise

        hook_instances = []
        mock_cfg = context.config.hooks.mock_btc_volatility
        mock_target = (mock_cfg.target or "root").strip().lower()
        if mock_target not in {"root", "expert"}:
            context.console.print("[yellow]Hook: invalid hooks.mockBtcVolatility.target, expected root|expert[/yellow]")
            mock_target = "root"

        if mock_cfg.enabled and mock_cfg.chat_id:
            if mock_target == "expert" and not mock_cfg.expert:
                context.console.print("[yellow]Hook: mock hook target=expert but expert is empty, hook disabled[/yellow]")
                mock_enabled = False
            else:
                mock_enabled = True
        else:
            mock_enabled = False

        if mock_enabled:
            mock_rule = HookRule(
                id="mock_btc_volatility",
                name="mock_btc_volatility",
                source="market.btc.mock",
                condition=HookCondition(kind="pct_change", gte=float(mock_cfg.threshold_pct)),
                target=HookTarget(kind=mock_target, expert=mock_cfg.expert),
                delivery=HookDelivery(
                    channel=mock_cfg.channel or "telegram",
                    chat_id=mock_cfg.chat_id,
                    deliver_result=mock_cfg.deliver_result,
                ),
                message_template="[Hook: {name}] BTC mock price moved {change_pct:.2f}% (from {previous_value} to {value})",
                cooldown_seconds=max(0, int(mock_cfg.cooldown_seconds)),
            )
            hook_instances.append(
                MockBtcVolatilityHook(
                    rule=mock_rule,
                    on_trigger=on_hook_trigger,
                    interval_s=max(5, int(mock_cfg.interval_seconds)),
                )
            )
        else:
            context.console.print("[dim]Hook: mock hook disabled (set hooks.mockBtcVolatility in config)[/dim]")

        self._hooks = HookManager(hook_instances)
        context.services["hook_manager"] = self._hooks
        context.services["hook_count"] = len(hook_instances)

    async def start(self, context: GatewayExtensionContext) -> None:
        await self._hooks.start()

    def stop(self, context: GatewayExtensionContext) -> None:
        self._hooks.stop()

    def status_line(self, context: GatewayExtensionContext) -> str | None:
        count = int(context.services.get("hook_count", 0))
        if count <= 0:
            return None
        return f"[green]\u2713[/green] Hooks: {count} code-defined"

    def status(self, context: GatewayExtensionContext) -> dict[str, Any]:
        """Return structured hook runtime status for observability."""
        hooks = getattr(self._hooks, "hooks", [])
        running_count = sum(1 for hook in hooks if bool(getattr(hook, "_running", False)))
        return {
            "status": "ok",
            "hook_count": int(context.services.get("hook_count", 0)),
            "running_hook_count": running_count,
            "trigger_count": self._trigger_count,
            "last_trigger_at": self._last_trigger_at.isoformat() if self._last_trigger_at else None,
            "last_error": self._last_error,
        }
