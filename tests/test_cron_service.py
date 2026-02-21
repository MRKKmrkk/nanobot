import pytest

from nanobot.cron.service import CronService
from nanobot.cron.types import CronSchedule
from nanobot.hooks.mock import MockBtcVolatilityHook
from nanobot.hooks.service import HookService
from nanobot.hooks.types import HookCondition, HookDelivery, HookRule, HookTarget


def test_add_job_rejects_unknown_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    with pytest.raises(ValueError, match="unknown timezone 'America/Vancovuer'"):
        service.add_job(
            name="tz typo",
            schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancovuer"),
            message="hello",
        )

    assert service.list_jobs(include_disabled=True) == []


def test_add_job_accepts_valid_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    job = service.add_job(
        name="tz ok",
        schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancouver"),
        message="hello",
    )

    assert job.schedule.tz == "America/Vancouver"
    assert job.state.next_run_at_ms is not None


@pytest.mark.asyncio
async def test_hook_pct_change_triggers_after_baseline(tmp_path) -> None:
    service = HookService(
        rules_path=tmp_path / "hooks" / "rules.json",
        state_path=tmp_path / "hooks" / "state.json",
    )
    service.add_rule(
        name="btc move",
        source="market.btc",
        gte_pct=2.0,
        channel="telegram",
        chat_id="123",
    )

    first = await service.process_value(source="market.btc", value=100.0, now_ms=1000)
    second = await service.process_value(source="market.btc", value=103.0, now_ms=2000)

    assert first == []
    assert len(second) == 1
    assert second[0].change_pct is not None
    assert second[0].change_pct > 2.0


@pytest.mark.asyncio
async def test_hook_cooldown_blocks_repeated_trigger(tmp_path) -> None:
    service = HookService(
        rules_path=tmp_path / "hooks" / "rules.json",
        state_path=tmp_path / "hooks" / "state.json",
    )
    service.add_rule(
        name="btc move",
        source="market.btc",
        gte_pct=1.0,
        channel="telegram",
        chat_id="123",
        cooldown_seconds=60,
    )

    await service.process_value(source="market.btc", value=100.0, now_ms=1000)
    t1 = await service.process_value(source="market.btc", value=102.0, now_ms=2000)
    t2 = await service.process_value(source="market.btc", value=104.0, now_ms=3000)
    t3 = await service.process_value(source="market.btc", value=106.0, now_ms=70000)

    assert len(t1) == 1
    assert t2 == []
    assert len(t3) == 1


def test_hook_add_requires_expert_name(tmp_path) -> None:
    service = HookService(
        rules_path=tmp_path / "hooks" / "rules.json",
        state_path=tmp_path / "hooks" / "state.json",
    )

    with pytest.raises(ValueError, match="target.expert is required"):
        service.add_rule(
            name="expert rule",
            source="market.btc",
            gte_pct=3.0,
            target_kind="expert",
            target_expert=None,
            channel="telegram",
            chat_id="123",
        )


@pytest.mark.asyncio
async def test_hook_callback_receives_event(tmp_path) -> None:
    calls = []

    async def on_trigger(rule, event):
        calls.append((rule.id, event.rule_id, event.source))
        return "ok"

    service = HookService(
        rules_path=tmp_path / "hooks" / "rules.json",
        state_path=tmp_path / "hooks" / "state.json",
        on_trigger=on_trigger,
    )
    rule = service.add_rule(
        name="btc move",
        source="market.btc",
        gte_pct=2.0,
        channel="telegram",
        chat_id="123",
    )

    await service.process_value(source="market.btc", value=100.0, now_ms=1000)
    await service.process_value(source="market.btc", value=103.0, now_ms=2000)

    assert calls == [(rule.id, rule.id, "market.btc")]


@pytest.mark.asyncio
async def test_mock_hook_ingest_value_triggers_callback() -> None:
    triggered = []

    async def on_trigger(rule, event):
        triggered.append((rule.id, event.source, event.change_pct))
        return "ok"

    rule = HookRule(
        id="mock_rule",
        name="mock_rule",
        source="market.btc.mock",
        condition=HookCondition(kind="pct_change", gte=2.0),
        target=HookTarget(kind="root"),
        delivery=HookDelivery(channel="telegram", chat_id="123", deliver_result=True),
        message_template="[Hook: {name}] delta={change_pct:.2f}%",
        cooldown_seconds=0,
    )
    hook = MockBtcVolatilityHook(rule=rule, on_trigger=on_trigger, interval_s=60, values=[100.0, 103.0])

    first = await hook.ingest_value(100.0, now_ms=1000)
    second = await hook.ingest_value(103.0, now_ms=2000)

    assert first is None
    assert second is not None
    assert len(triggered) == 1
    assert triggered[0][0] == "mock_rule"
