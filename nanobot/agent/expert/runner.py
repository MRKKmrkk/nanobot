"""Expert agent runner."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.expert.experts import ExpertDef, ExpertLoader
from nanobot.agent.expert.context import ExpertContextBuilder
from nanobot.agent.expert.tools import build_expert_tools
from nanobot.agent.memory import MemoryStore
from nanobot.agent.memory_consolidator import MemoryConsolidator
from nanobot.session.manager import SessionManager
from nanobot.agent.context import ContextBuilder
from nanobot.utils.helpers import get_experts_path


class ExpertRunner:
    """Run expert agents synchronously."""

    def __init__(
        self,
        provider,
        workspace: Path,
        model: str,
        temperature: float,
        max_tokens: int,
        max_iterations: int,
        memory_window: int,
        brave_api_key: str | None,
        exec_config,
        restrict_to_workspace: bool,
        main_session_manager: SessionManager,
    ):
        self.provider = provider
        self.workspace = workspace
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_iterations = max_iterations
        self.memory_window = memory_window
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config
        self.restrict_to_workspace = restrict_to_workspace
        self.main_sessions = main_session_manager
        self._loader = ExpertLoader(workspace)
        self._context = ExpertContextBuilder(workspace)
        self._base_context = ContextBuilder(workspace)
        self._expert_sessions: dict[str, SessionManager] = {}
        self._expert_consolidators: dict[str, MemoryConsolidator] = {}

    async def run(
        self,
        expert_name: str,
        message: str,
        *,
        session_key: str | None,
        channel: str,
        chat_id: str,
        override: dict[str, Any] | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str, list[str]]:
        """Run one expert conversation turn and return (final_content, tools_used)."""
        expert = self._loader.load(expert_name)
        if override:
            expert = self._apply_override(expert, override)

        effective_model = expert.model or self.model
        effective_temperature = expert.temperature if expert.temperature is not None else self.temperature
        effective_max_tokens = expert.max_tokens if expert.max_tokens is not None else self.max_tokens
        effective_max_iterations = expert.max_tool_iterations if expert.max_tool_iterations is not None else self.max_iterations

        tools = build_expert_tools(
            expert,
            self.workspace,
            brave_api_key=self.brave_api_key,
            exec_timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
        )

        inherited_system = None
        inherited_history = None
        inherited_memory = None

        if session_key and expert.inherit_context:
            session = self.main_sessions.get_or_create(session_key)
            inherited_history = session.get_history(max_messages=self.memory_window)
            inherited_system = self._base_context.build_runtime_constraints_prompt(
                include_main_memory_refs=False
            )

        if expert.memory_mode == "isolated_long_term":
            inherited_memory = self._get_expert_memory(expert).get_memory_context()

        include_memory = expert.memory_mode == "isolated_long_term"

        messages = self._context.build_messages(
            expert,
            current_message=message,
            inherited_history=inherited_history,
            include_memory=include_memory,
            inherit_context=expert.inherit_context,
            inherited_system=inherited_system,
            inherited_memory=inherited_memory,
        )

        final_content, tools_used = await self._run_loop(
            messages=messages,
            tool_registry=tools,
            tool_defs=tools.get_definitions(),
            max_iterations=effective_max_iterations,
            model=effective_model,
            temperature=effective_temperature,
            max_tokens=effective_max_tokens,
            on_progress=on_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        if expert.memory_mode != "ephemeral":
            self._persist_session(
                expert=expert,
                session_key=session_key or f"{channel}:{chat_id}",
                user_message=message,
                assistant_message=final_content,
                tools_used=tools_used,
            )

        return final_content, tools_used

    async def _run_loop(
        self,
        *,
        messages: list[dict[str, Any]],
        tool_registry,
        tool_defs: list[dict[str, Any]],
        max_iterations: int,
        model: str,
        temperature: float,
        max_tokens: int,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str]]:
        """Execute the expert tool-calling loop until completion or iteration limit."""
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        text_only_retried = False

        while iteration < max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=tool_defs,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if response.has_tool_calls:
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls))

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
                messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": tool_call_dicts,
                })

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Expert tool call: {}({})", tool_call.name, args_str[:200])
                    result = await tool_registry.execute(tool_call.name, tool_call.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.name,
                        "content": result,
                    })
            else:
                final_content = self._strip_think(response.content)
                if not tools_used and not text_only_retried and final_content:
                    text_only_retried = True
                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                    })
                    final_content = None
                    continue
                break

        return final_content, tools_used

    def _persist_session(
        self,
        *,
        expert: ExpertDef,
        session_key: str,
        user_message: str,
        assistant_message: str,
        tools_used: list[str],
    ) -> None:
        """Persist expert messages and trigger async consolidation when needed."""
        sessions = self._get_expert_sessions(expert)
        session = sessions.get_or_create(session_key)
        session.add_message("user", user_message)
        session.add_message("assistant", assistant_message, tools_used=tools_used or None)
        sessions.save(session)

        if len(session.messages) > self.memory_window:
            consolidator = self._get_expert_consolidator(expert)
            try:
                import asyncio
                asyncio.create_task(consolidator.consolidate(session))
            except RuntimeError:
                # No running loop; skip consolidation.
                pass

    def _get_expert_sessions(self, expert: ExpertDef) -> SessionManager:
        """Get or create the session manager rooted at ``experts/<name>``."""
        if expert.dir_name in self._expert_sessions:
            return self._expert_sessions[expert.dir_name]
        expert_dir = get_experts_path(self.workspace) / expert.dir_name
        sessions = SessionManager(expert_dir)
        self._expert_sessions[expert.dir_name] = sessions
        return sessions

    def _get_expert_memory(self, expert: ExpertDef) -> MemoryStore:
        """Get the expert-local memory store under ``experts/<name>/memory``."""
        expert_dir = get_experts_path(self.workspace) / expert.dir_name
        return MemoryStore(expert_dir)

    def _get_expert_consolidator(self, expert: ExpertDef) -> MemoryConsolidator:
        """Get or create the expert-local memory consolidator."""
        if expert.dir_name in self._expert_consolidators:
            return self._expert_consolidators[expert.dir_name]
        consolidator = MemoryConsolidator(
            provider=self.provider,
            model=self.model,
            memory_window=self.memory_window,
            memory_store=self._get_expert_memory(expert),
        )
        self._expert_consolidators[expert.dir_name] = consolidator
        return consolidator

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove model `<think>...</think>` blocks from response text."""
        if not text:
            return None
        return re.sub(r"<think>[\\s\\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as a short progress hint string."""
        def _fmt(tc):
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _apply_override(expert: ExpertDef, override: dict[str, Any]) -> ExpertDef:
        """Create a derived expert definition with per-call overrides."""
        tools = override.get("tools", {}) if isinstance(override.get("tools"), dict) else {}
        return ExpertDef(
            dir_name=expert.dir_name,
            name=override.get("name", expert.name),
            description=override.get("description", expert.description),
            prompt=override.get("prompt", expert.prompt),
            tools_allow=override.get("tools_allow", tools.get("allow", expert.tools_allow)),
            tools_deny=override.get("tools_deny", tools.get("deny", expert.tools_deny)),
            memory_mode=override.get("memory_mode", expert.memory_mode),
            inherit_context=override.get("inherit_context", expert.inherit_context),
            model=override.get("model", expert.model),
            temperature=override.get("temperature", expert.temperature),
            max_tokens=override.get("max_tokens", expert.max_tokens),
            max_tool_iterations=override.get("max_tool_iterations", expert.max_tool_iterations),
        )
