"""Memory consolidation helper for sessions."""

from __future__ import annotations

import json

import json_repair
from loguru import logger

from nanobot.agent.memory import MemoryStore


class MemoryConsolidator:
    """Consolidate session history into long-term memory + history log."""

    def __init__(self, provider, model: str, memory_window: int, memory_store: MemoryStore):
        self.provider = provider
        self.model = model
        self.memory_window = memory_window
        self.memory_store = memory_store

    async def consolidate(self, session, archive_all: bool = False) -> None:
        memory = self.memory_store

        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info("Memory consolidation (archive_all): {} total messages archived", len(session.messages))
        else:
            keep_count = self.memory_window // 2
            if len(session.messages) <= keep_count:
                logger.debug(
                    "Session {}: No consolidation needed (messages={}, keep={})",
                    session.key,
                    len(session.messages),
                    keep_count,
                )
                return

            messages_to_process = len(session.messages) - session.last_consolidated
            if messages_to_process <= 0:
                logger.debug(
                    "Session {}: No new messages to consolidate (last_consolidated={}, total={})",
                    session.key,
                    session.last_consolidated,
                    len(session.messages),
                )
                return

            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return
            logger.info(
                "Memory consolidation started: {} total, {} new to consolidate, {} keep",
                len(session.messages),
                len(old_messages),
                keep_count,
            )

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}")
        conversation = "\n".join(lines)
        current_memory = memory.read_long_term()

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly two keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM]. Include enough detail to be useful when found by grep search later.

2. "memory_update": The updated long-term memory content. Add any new facts: user location, preferences, personal info, habits, project context, technical decisions, tools/services used. If nothing new, return the existing content unchanged.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{conversation}

**IMPORTANT**: Both values MUST be strings, not objects or arrays.

Example:
{{
  "history_entry": "[2026-02-14 22:50] User asked about...",
  "memory_update": "- Host: HARRYBOOK-T14P\\n- Name: Nado"
}}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "You are a memory consolidation agent. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model,
            )
            text = (response.content or "").strip()
            if not text:
                logger.warning("Memory consolidation: LLM returned empty response, skipping")
                return
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(text)
            if not isinstance(result, dict):
                logger.warning("Memory consolidation: unexpected response type, skipping. Response: {}", text[:200])
                return

            if entry := result.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                memory.append_history(entry)
            if update := result.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    memory.write_long_term(update)

            if archive_all:
                session.last_consolidated = 0
            else:
                session.last_consolidated = len(session.messages) - keep_count
            logger.info(
                "Memory consolidation done: {} messages, last_consolidated={}",
                len(session.messages),
                session.last_consolidated,
            )
        except Exception as e:
            logger.error("Memory consolidation failed: {}", e)
