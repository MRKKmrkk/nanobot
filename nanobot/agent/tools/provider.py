"""Provider management tool: switch LLM provider at runtime."""

from __future__ import annotations

from typing import Any, Callable

from nanobot.agent.tools.base import Tool


class SwitchLLMProviderTool(Tool):
    """Tool to switch the active LLM provider (and optional model)."""

    def __init__(self, switch_callback: Callable[[Any, str | None], None], config_path=None):
        self._switch_callback = switch_callback
        self._config_path = config_path

    @property
    def name(self) -> str:
        return "switch_llm_provider"

    @property
    def description(self) -> str:
        return (
            "Switch the active LLM provider for this agent. "
            "Optionally set the default model and persist to config."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        from nanobot.providers.registry import PROVIDERS

        providers = ["auto"] + [spec.name.replace("_", "-") for spec in PROVIDERS]
        return {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Provider name (use 'auto' for auto-detection).",
                    "enum": providers,
                },
                "model": {
                    "type": "string",
                    "description": "Optional model name to set as default.",
                },
                "persist": {
                    "type": "boolean",
                    "description": "Persist change to ~/.nanobot/config.json.",
                    "default": True,
                },
            },
            "required": ["provider"],
        }

    async def execute(self, provider: str, model: str | None = None, persist: bool = True, **kwargs: Any) -> str:
        """Switch provider and optionally update model."""
        from nanobot.config.loader import load_config, save_config
        from nanobot.providers.factory import make_provider
        from nanobot.providers.registry import PROVIDERS, find_by_name

        normalized = provider.strip().lower()
        if normalized != "auto":
            normalized = normalized.replace("-", "_")
            if not find_by_name(normalized):
                names = ", ".join(spec.name.replace("_", "-") for spec in PROVIDERS)
                return f"Error: Unknown provider '{provider}'. Supported: {names}, auto."

        config = load_config(self._config_path)
        config.agents.defaults.provider = "auto" if normalized == "auto" else normalized
        if model:
            config.agents.defaults.model = model

        try:
            new_provider = make_provider(config, require_api_key=True)
        except ValueError:
            return (
                "Error: No API key configured for the selected provider. "
                "Set one in ~/.nanobot/config.json under providers section."
            )

        self._switch_callback(new_provider, config.agents.defaults.model)

        if persist:
            save_config(config, self._config_path)
            return (
                f"Switched provider to '{config.agents.defaults.provider}' "
                f"with model '{config.agents.defaults.model}' (saved)."
            )

        return (
            f"Switched provider to '{config.agents.defaults.provider}' "
            f"with model '{config.agents.defaults.model}' (not saved)."
        )


class ProviderInfoTool(Tool):
    """Tool to report current provider and list available providers."""

    def __init__(self, get_info: Callable[[], dict[str, Any]]):
        self._get_info = get_info

    @property
    def name(self) -> str:
        return "get_provider_info"

    @property
    def description(self) -> str:
        return "Get the current provider/model and list available providers."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        info = self._get_info()
        current = info.get("current_provider") or "unknown"
        model = info.get("current_model") or "unknown"
        available = info.get("available") or []
        available_text = ", ".join(available) if available else "(none)"
        return f"Current provider: '{current}', model: '{model}'. Available providers: {available_text}."
