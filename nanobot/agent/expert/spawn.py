"""Expert spawn manager for background execution."""

from __future__ import annotations

import asyncio
import uuid

from loguru import logger

from nanobot.bus.events import InboundMessage


class ExpertSpawnManager:
    """Run expert tasks asynchronously and report results."""

    def __init__(self, runner, bus):
        self.runner = runner
        self.bus = bus
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

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
        """Start one background expert task and return a launch message."""
        task_id = str(uuid.uuid4())[:8]
        display_label = label or f"{expert}: {message[:30]}" + ("..." if len(message) > 30 else "")
        origin = {"channel": origin_channel, "chat_id": origin_chat_id}

        bg_task = asyncio.create_task(
            self._run_expert(task_id, expert, message, display_label, origin, session_key)
        )
        self._running_tasks[task_id] = bg_task
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))

        logger.info("Spawned expert [{}]: {}", task_id, display_label)
        return f"Expert [{display_label}] started (id: {task_id}). I'll notify you when it completes."

    async def _run_expert(
        self,
        task_id: str,
        expert: str,
        message: str,
        label: str,
        origin: dict[str, str],
        session_key: str | None,
    ) -> None:
        """Execute expert task and publish success/error announcement."""
        logger.info("Expert [{}] starting task: {}", task_id, label)
        try:
            result, _ = await self.runner.run(
                expert_name=expert,
                message=message,
                session_key=session_key,
                channel=origin["channel"],
                chat_id=origin["chat_id"],
            )
            await self._announce_result(task_id, label, expert, message, result, origin, "ok")
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error("Expert [{}] failed: {}", task_id, e)
            await self._announce_result(task_id, label, expert, message, error_msg, origin, "error")

    async def _announce_result(
        self,
        task_id: str,
        label: str,
        expert: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        """Publish a system message so the main agent can summarize to user."""
        status_text = "completed successfully" if status == "ok" else "failed"

        announce_content = f"""[Expert '{label}' {status_text}]

Expert: {expert}
Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like \"expert\" or task IDs."""

        msg = InboundMessage(
            channel="system",
            sender_id="expert",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
        )
        await self.bus.publish_inbound(msg)
        logger.debug("Expert [{}] announced result to {}:{}", task_id, origin["channel"], origin["chat_id"])

    def get_running_count(self) -> int:
        """Return the number of currently running expert tasks."""
        return len(self._running_tasks)
