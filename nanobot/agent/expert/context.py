"""Context builder for expert agents."""

from __future__ import annotations

from typing import Any

from nanobot.agent.context import ContextBuilder
from nanobot.agent.expert.experts import ExpertDef


class ExpertContextBuilder:
    """Build system prompt and messages for experts."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.base = ContextBuilder(workspace)

    def build_system_prompt(
        self,
        expert: ExpertDef,
        *,
        include_memory: bool,
        inherit_context: bool,
        inherited_system: str | None = None,
        inherited_memory: str | None = None,
    ) -> str:
        """Build the final expert system prompt for one run."""
        parts: list[str] = []

        if inherit_context and inherited_system:
            parts.append(inherited_system)
        else:
            # Keep runtime/safety constraints but avoid importing nanobot identity.
            parts.append(self.base.build_runtime_constraints_prompt(include_main_memory_refs=False))

        parts.append(
            f"# Expert Identity: {expert.name}\n\n"
            f"{expert.prompt}\n\n"
            "Conflict rule: if any inherited instruction conflicts with this Expert Identity section, "
            "follow Expert Identity."
        )

        if include_memory:
            if inherited_memory is not None:
                memory_text = inherited_memory
            else:
                memory_text = ""
            if memory_text:
                parts.append(f"# Expert Memory\n\n{memory_text}")

        return "\n\n---\n\n".join(parts)

    def build_messages(
        self,
        expert: ExpertDef,
        *,
        current_message: str,
        inherited_history: list[dict[str, Any]] | None = None,
        include_memory: bool,
        inherit_context: bool,
        inherited_system: str | None = None,
        inherited_memory: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build chat messages for expert execution."""
        system_prompt = self.build_system_prompt(
            expert,
            include_memory=include_memory,
            inherit_context=inherit_context,
            inherited_system=inherited_system,
            inherited_memory=inherited_memory,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if inherit_context and inherited_history:
            messages.extend(inherited_history)
        messages.append({"role": "user", "content": current_message})
        return messages
