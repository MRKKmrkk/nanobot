"""Extension abstractions for gateway lifecycle hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from nanobot.config.schema import Config


@dataclass
class GatewayExtensionContext:
    """Runtime objects exposed to extensions."""

    config: Config
    workspace: Path
    console: Console
    agent: Any
    bus: Any
    services: dict[str, Any] = field(default_factory=dict)


class NanobotExtension:
    """Base class for gateway extensions."""

    extension_id = "base"

    def configure(self, context: GatewayExtensionContext) -> None:
        """Configure extension with gateway context before startup."""

    async def start(self, context: GatewayExtensionContext) -> None:
        """Start extension background tasks/services."""

    def stop(self, context: GatewayExtensionContext) -> None:
        """Stop extension background tasks/services."""

    def status_line(self, context: GatewayExtensionContext) -> str | None:
        """Return one status line for startup output."""
        return None

    def status(self, context: GatewayExtensionContext) -> dict[str, Any]:
        """Return structured runtime status for observability."""
        return {}
