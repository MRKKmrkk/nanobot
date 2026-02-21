"""Expert extension entrypoint."""

from __future__ import annotations

from typing import Any

from nanobot.agent.expert.experts import ExpertLoader
from nanobot.extensions.base import GatewayExtensionContext, NanobotExtension


class ExpertExtension(NanobotExtension):
    """Expose expert capability metadata for gateway status."""

    extension_id = "expert"

    def status_line(self, context: GatewayExtensionContext) -> str | None:
        loader = ExpertLoader(context.workspace)
        count = len(loader.list_experts())
        if count <= 0:
            return None
        return f"[green]\u2713[/green] Experts: {count} available"

    def status(self, context: GatewayExtensionContext) -> dict[str, Any]:
        """Return structured expert runtime status for observability."""
        loader = ExpertLoader(context.workspace)
        experts = loader.list_experts()
        return {
            "status": "ok",
            "experts_count": len(experts),
            "experts": experts,
        }
