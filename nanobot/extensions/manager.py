"""Gateway extension manager."""

from __future__ import annotations

from loguru import logger

from nanobot.extensions.base import GatewayExtensionContext, NanobotExtension


class ExtensionManager:
    """Manage extension lifecycle with fault isolation."""

    def __init__(self, extensions: list[NanobotExtension] | None = None):
        self.extensions = extensions or []

    def configure_all(self, context: GatewayExtensionContext) -> None:
        """Configure all extensions."""
        for ext in self.extensions:
            try:
                ext.configure(context)
            except Exception as e:
                logger.error("Extension configure failed ({}): {}", ext.extension_id, e)

    async def start_all(self, context: GatewayExtensionContext) -> None:
        """Start all extensions."""
        for ext in self.extensions:
            try:
                await ext.start(context)
            except Exception as e:
                logger.error("Extension start failed ({}): {}", ext.extension_id, e)

    def stop_all(self, context: GatewayExtensionContext) -> None:
        """Stop all extensions."""
        for ext in self.extensions:
            try:
                ext.stop(context)
            except Exception as e:
                logger.error("Extension stop failed ({}): {}", ext.extension_id, e)

    def status_lines(self, context: GatewayExtensionContext) -> list[str]:
        """Collect startup status lines from extensions."""
        lines: list[str] = []
        for ext in self.extensions:
            try:
                line = ext.status_line(context)
            except Exception:
                line = None
            if line:
                lines.append(line)
        return lines

    def status_snapshot(self, context: GatewayExtensionContext) -> dict[str, dict]:
        """Collect structured status from all extensions."""
        snapshot: dict[str, dict] = {}
        for ext in self.extensions:
            try:
                data = ext.status(context)
            except Exception as e:
                data = {"status": "error", "last_error": str(e)}
            snapshot[ext.extension_id] = data
        return snapshot
