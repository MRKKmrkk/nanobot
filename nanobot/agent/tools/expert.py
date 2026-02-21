"""Tools for interacting with expert agents."""

from __future__ import annotations

from typing import Any, Protocol

from nanobot.agent.tools.base import Tool


class ExpertRuntimeProtocol(Protocol):
    """Minimal protocol required by expert tools."""

    async def chat(
        self,
        *,
        expert_name: str,
        message: str,
        session_key: str | None,
        channel: str,
        chat_id: str,
        override: dict | None = None,
    ) -> tuple[str, list[str]]:
        ...

    async def spawn(
        self,
        *,
        expert: str,
        message: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
    ) -> str:
        ...


class ExpertChatTool(Tool):
    """Chat with an expert agent synchronously."""

    def __init__(self, runtime: ExpertRuntimeProtocol):
        self._runtime = runtime
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
        self._session_key: str | None = None

    def set_context(self, channel: str, chat_id: str, session_key: str | None) -> None:
        """Set request context used for expert execution."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id
        self._session_key = session_key

    @property
    def name(self) -> str:
        return "expert_chat"

    @property
    def description(self) -> str:
        return (
            "Chat with a specialized expert agent. Use this when a task benefits from a "
            "custom prompt or a restricted toolset."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expert": {"type": "string", "description": "Expert name (directory in workspace/experts)"},
                "message": {"type": "string", "description": "Message to send to the expert"},
                "override": {
                    "type": "object",
                    "description": "Optional overrides (model/temperature/tools/memory)",
                },
            },
            "required": ["expert", "message"],
        }

    async def execute(self, expert: str, message: str, override: dict | None = None, **kwargs: Any) -> str:
        """Run expert synchronously and return its final response."""
        result, _ = await self._runtime.chat(
            expert_name=expert,
            message=message,
            session_key=self._session_key,
            channel=self._origin_channel,
            chat_id=self._origin_chat_id,
            override=override,
        )
        return result


class ExpertSpawnTool(Tool):
    """Spawn an expert agent in the background."""

    def __init__(self, runtime: ExpertRuntimeProtocol):
        self._runtime = runtime
        self._origin_channel = "cli"
        self._origin_chat_id = "direct"
        self._session_key: str | None = None

    def set_context(self, channel: str, chat_id: str, session_key: str | None) -> None:
        """Set origin context for background expert result routing."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id
        self._session_key = session_key

    @property
    def name(self) -> str:
        return "expert_spawn"

    @property
    def description(self) -> str:
        return (
            "Spawn an expert agent to run a task in the background. "
            "The expert will report back when it completes."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expert": {"type": "string", "description": "Expert name (directory in workspace/experts)"},
                "message": {"type": "string", "description": "Task/message for the expert"},
                "label": {"type": "string", "description": "Optional short label for the task"},
            },
            "required": ["expert", "message"],
        }

    async def execute(self, expert: str, message: str, label: str | None = None, **kwargs: Any) -> str:
        """Launch background expert task and return launch status text."""
        return await self._runtime.spawn(
            expert=expert,
            message=message,
            label=label,
            origin_channel=self._origin_channel,
            origin_chat_id=self._origin_chat_id,
            session_key=self._session_key,
        )
