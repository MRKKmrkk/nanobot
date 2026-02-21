import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from nanobot.cli.commands import _dispatch_hook_event, app
from nanobot.config.schema import Config
from nanobot.extensions.base import GatewayExtensionContext, NanobotExtension
from nanobot.extensions.manager import ExtensionManager
from nanobot.extensions.hook_extension import HookExtension
from nanobot.extensions.registry import (
    default_gateway_extension_specs,
    load_gateway_extensions,
)
from nanobot.hooks.types import HookCondition, HookDelivery, HookEvent, HookRule, HookTarget
from nanobot.providers.litellm_provider import LiteLLMProvider
from nanobot.providers.openai_codex_provider import _strip_model_prefix
from nanobot.providers.registry import find_by_model

runner = CliRunner()


@pytest.fixture
def mock_paths():
    """Mock config/workspace paths for test isolation."""
    with patch("nanobot.config.loader.get_config_path") as mock_cp, \
         patch("nanobot.config.loader.save_config") as mock_sc, \
         patch("nanobot.config.loader.load_config") as mock_lc, \
         patch("nanobot.utils.helpers.get_workspace_path") as mock_ws:

        base_dir = Path("./test_onboard_data")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir()

        config_file = base_dir / "config.json"
        workspace_dir = base_dir / "workspace"

        mock_cp.return_value = config_file
        mock_ws.return_value = workspace_dir
        mock_sc.side_effect = lambda config: config_file.write_text("{}")

        yield config_file, workspace_dir

        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_onboard_fresh_install(mock_paths):
    """No existing config — should create from scratch."""
    config_file, workspace_dir = mock_paths

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert "Created config" in result.stdout
    assert "Created workspace" in result.stdout
    assert "nanobot is ready" in result.stdout
    assert config_file.exists()
    assert (workspace_dir / "AGENTS.md").exists()
    assert (workspace_dir / "memory" / "MEMORY.md").exists()


def test_onboard_existing_config_refresh(mock_paths):
    """Config exists, user declines overwrite — should refresh (load-merge-save)."""
    config_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "existing values preserved" in result.stdout
    assert workspace_dir.exists()
    assert (workspace_dir / "AGENTS.md").exists()


def test_onboard_existing_config_overwrite(mock_paths):
    """Config exists, user confirms overwrite — should reset to defaults."""
    config_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="y\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "Config reset to defaults" in result.stdout
    assert workspace_dir.exists()


def test_onboard_existing_workspace_safe_create(mock_paths):
    """Workspace exists — should not recreate, but still add missing templates."""
    config_file, workspace_dir = mock_paths
    workspace_dir.mkdir(parents=True)
    config_file.write_text("{}")

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Created workspace" not in result.stdout
    assert "Created AGENTS.md" in result.stdout
    assert (workspace_dir / "AGENTS.md").exists()


def test_status_shows_extension_snapshot(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{}")
    cfg = Config()
    cfg.agents.defaults.workspace = str(tmp_path / "workspace")

    with patch("nanobot.config.loader.get_config_path", return_value=config_file), patch(
        "nanobot.config.loader.load_config", return_value=cfg
    ):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "Extensions:" in result.stdout


def test_config_matches_github_copilot_codex_with_hyphen_prefix():
    config = Config()
    config.agents.defaults.model = "github-copilot/gpt-5.3-codex"

    assert config.get_provider_name() == "github_copilot"


def test_config_matches_openai_codex_with_hyphen_prefix():
    config = Config()
    config.agents.defaults.model = "openai-codex/gpt-5.1-codex"

    assert config.get_provider_name() == "openai_codex"


def test_find_by_model_prefers_explicit_prefix_over_generic_codex_keyword():
    spec = find_by_model("github-copilot/gpt-5.3-codex")

    assert spec is not None
    assert spec.name == "github_copilot"


def test_litellm_provider_canonicalizes_github_copilot_hyphen_prefix():
    provider = LiteLLMProvider(default_model="github-copilot/gpt-5.3-codex")

    resolved = provider._resolve_model("github-copilot/gpt-5.3-codex")

    assert resolved == "github_copilot/gpt-5.3-codex"


def test_openai_codex_strip_prefix_supports_hyphen_and_underscore():
    assert _strip_model_prefix("openai-codex/gpt-5.1-codex") == "gpt-5.1-codex"
    assert _strip_model_prefix("openai_codex/gpt-5.1-codex") == "gpt-5.1-codex"


def test_config_supports_mock_hook_settings():
    cfg = Config.model_validate(
        {
            "hooks": {
                "mockBtcVolatility": {
                    "enabled": True,
                    "channel": "telegram",
                    "chatId": "123",
                    "intervalSeconds": 10,
                    "thresholdPct": 1.5,
                    "cooldownSeconds": 20,
                    "target": "expert",
                    "expert": "sec",
                    "deliverResult": False,
                }
            }
        }
    )
    hook = cfg.hooks.mock_btc_volatility
    assert hook.enabled is True
    assert hook.chat_id == "123"
    assert hook.target == "expert"
    assert hook.expert == "sec"
    assert hook.deliver_result is False


def test_config_supports_gateway_extensions_declaration():
    cfg = Config.model_validate(
        {
            "gateway": {
                "extensions": [
                    {
                        "extensionId": "expert",
                        "classPath": "nanobot.extensions.expert_extension.ExpertExtension",
                        "enabled": True,
                    },
                    {
                        "extensionId": "hook",
                        "classPath": "nanobot.extensions.hook_extension.HookExtension",
                        "enabled": False,
                    },
                ]
            }
        }
    )
    assert len(cfg.gateway.extensions) == 2
    assert cfg.gateway.extensions[0].extension_id == "expert"
    assert cfg.gateway.extensions[1].enabled is False


@pytest.mark.asyncio
async def test_dispatch_hook_event_routes_to_root_and_delivers() -> None:
    class _FakeBus:
        def __init__(self):
            self.outbound = []

        async def publish_outbound(self, msg):
            self.outbound.append(msg)

    class _FakeAgent:
        def __init__(self):
            self.hook_calls = []

        async def process_inbound(self, msg, **kwargs):
            self.hook_calls.append((msg.content, kwargs))
            return "root-result"

    agent = _FakeAgent()
    bus = _FakeBus()
    rule = HookRule(
        id="r1",
        name="r1",
        source="market.btc",
        condition=HookCondition(kind="pct_change", gte=2.0),
        target=HookTarget(kind="root"),
        delivery=HookDelivery(channel="telegram", chat_id="123", deliver_result=True),
    )
    event = HookEvent(
        rule_id="r1",
        source="market.btc",
        value=103.0,
        previous_value=100.0,
        change_pct=3.0,
        rendered_message="hook msg",
    )

    result = await _dispatch_hook_event(agent, bus, rule, event)
    assert result == "root-result"
    assert len(agent.hook_calls) == 1
    assert len(bus.outbound) == 1
    assert bus.outbound[0].content == "root-result"
    assert bus.outbound[0].metadata.get("origin") == "hook"


@pytest.mark.asyncio
async def test_dispatch_hook_event_routes_to_expert_without_delivery() -> None:
    class _FakeBus:
        def __init__(self):
            self.outbound = []

        async def publish_outbound(self, msg):
            self.outbound.append(msg)

    class _FakeRuntime:
        def __init__(self):
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return "expert-result", []

    class _FakeAgent:
        def __init__(self):
            self.expert_runtime = _FakeRuntime()

    agent = _FakeAgent()
    bus = _FakeBus()
    rule = HookRule(
        id="r2",
        name="r2",
        source="market.btc",
        condition=HookCondition(kind="pct_change", gte=2.0),
        target=HookTarget(kind="expert", expert="sec"),
        delivery=HookDelivery(channel="telegram", chat_id="123", deliver_result=False),
    )
    event = HookEvent(
        rule_id="r2",
        source="market.btc",
        value=97.0,
        previous_value=100.0,
        change_pct=-3.0,
        rendered_message="hook msg 2",
    )

    result = await _dispatch_hook_event(agent, bus, rule, event)
    assert result == "expert-result"
    assert len(agent.expert_runtime.calls) == 1
    assert bus.outbound == []


@pytest.mark.asyncio
async def test_dispatch_hook_event_skips_empty_delivery() -> None:
    class _FakeBus:
        def __init__(self):
            self.outbound = []

        async def publish_outbound(self, msg):
            self.outbound.append(msg)

    class _FakeAgent:
        async def process_inbound(self, msg, **kwargs):
            return ""

    agent = _FakeAgent()
    bus = _FakeBus()
    rule = HookRule(
        id="r3",
        name="r3",
        source="market.btc",
        condition=HookCondition(kind="pct_change", gte=2.0),
        target=HookTarget(kind="root"),
        delivery=HookDelivery(channel="telegram", chat_id="123", deliver_result=True),
    )
    event = HookEvent(
        rule_id="r3",
        source="market.btc",
        value=103.0,
        previous_value=100.0,
        change_pct=3.0,
        rendered_message="hook msg",
    )

    result = await _dispatch_hook_event(agent, bus, rule, event)
    assert result == ""
    assert bus.outbound == []


def test_default_gateway_extension_specs_contains_expert_and_hook() -> None:
    ids = [spec.extension_id for spec in default_gateway_extension_specs()]
    assert "expert" in ids
    assert "hook" in ids


def test_load_gateway_extensions_respects_enabled_switch() -> None:
    cfg = Config.model_validate(
        {
            "gateway": {
                "extensions": [
                    {
                        "extensionId": "expert",
                        "classPath": "nanobot.extensions.expert_extension.ExpertExtension",
                        "enabled": True,
                    },
                    {
                        "extensionId": "hook",
                        "classPath": "nanobot.extensions.hook_extension.HookExtension",
                        "enabled": False,
                    },
                ]
            }
        }
    )
    exts = load_gateway_extensions(cfg)
    ids = [ext.extension_id for ext in exts]
    assert ids == ["expert"]


def test_load_gateway_extensions_falls_back_to_defaults_when_empty() -> None:
    exts = load_gateway_extensions(Config())
    ids = {ext.extension_id for ext in exts}
    assert {"expert", "hook"}.issubset(ids)


def test_load_gateway_extensions_explicit_empty_disables_all() -> None:
    cfg = Config.model_validate({"gateway": {"extensions": []}})
    exts = load_gateway_extensions(cfg)
    assert exts == []


@pytest.mark.asyncio
async def test_extension_manager_lifecycle_and_isolation(tmp_path) -> None:
    calls: list[str] = []

    class _GoodExt(NanobotExtension):
        extension_id = "good"

        def configure(self, context: GatewayExtensionContext) -> None:
            calls.append("good:configure")

        async def start(self, context: GatewayExtensionContext) -> None:
            calls.append("good:start")

        def stop(self, context: GatewayExtensionContext) -> None:
            calls.append("good:stop")

        def status_line(self, context: GatewayExtensionContext) -> str | None:
            return "good:ok"

    class _BadExt(NanobotExtension):
        extension_id = "bad"

        def configure(self, context: GatewayExtensionContext) -> None:
            raise RuntimeError("boom configure")

        async def start(self, context: GatewayExtensionContext) -> None:
            raise RuntimeError("boom start")

        def stop(self, context: GatewayExtensionContext) -> None:
            raise RuntimeError("boom stop")

    ctx = GatewayExtensionContext(
        config=Config(),
        workspace=tmp_path,
        console=None,  # type: ignore[arg-type]
        agent=object(),
        bus=object(),
    )
    mgr = ExtensionManager([_BadExt(), _GoodExt()])
    mgr.configure_all(ctx)
    await mgr.start_all(ctx)
    mgr.stop_all(ctx)

    assert calls == ["good:configure", "good:start", "good:stop"]
    assert mgr.status_lines(ctx) == ["good:ok"]


@pytest.mark.asyncio
async def test_extension_manager_hook_chain_integration(tmp_path) -> None:
    class _DummyConsole:
        def print(self, *args, **kwargs):
            return None

    class _FakeBus:
        def __init__(self):
            self.outbound = []

        async def publish_outbound(self, msg):
            self.outbound.append(msg)

    class _FakeAgent:
        def __init__(self):
            self.calls = []

        async def process_inbound(self, msg, **kwargs):
            self.calls.append((msg.content, kwargs))
            return "handled-by-root"

    cfg = Config.model_validate(
        {
            "hooks": {
                "mockBtcVolatility": {
                    "enabled": True,
                    "channel": "telegram",
                    "chatId": "123",
                    "thresholdPct": 2.0,
                    "cooldownSeconds": 0,
                    "deliverResult": True,
                }
            }
        }
    )
    ctx = GatewayExtensionContext(
        config=cfg,
        workspace=tmp_path,
        console=_DummyConsole(),  # type: ignore[arg-type]
        agent=_FakeAgent(),
        bus=_FakeBus(),
    )
    ext = HookExtension()
    mgr = ExtensionManager([ext])
    mgr.configure_all(ctx)
    await mgr.start_all(ctx)

    hook_manager = ctx.services["hook_manager"]
    mock_hook = hook_manager.hooks[0]
    first = await mock_hook.ingest_value(100.0, now_ms=1000)
    second = await mock_hook.ingest_value(103.0, now_ms=2000)
    mgr.stop_all(ctx)

    assert first is None
    assert second is not None
    assert len(ctx.agent.calls) == 1
    assert len(ctx.bus.outbound) == 1
    snapshot = mgr.status_snapshot(ctx)
    assert snapshot["hook"]["hook_count"] == 1
    assert snapshot["hook"]["trigger_count"] >= 1
