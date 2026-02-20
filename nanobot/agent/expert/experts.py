"""Expert definitions and loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanobot.utils.helpers import ensure_dir, get_experts_path


@dataclass(frozen=True)
class ExpertDef:
    dir_name: str
    name: str
    description: str
    prompt: str
    tools_allow: list[str] | None
    tools_deny: list[str] | None
    memory_mode: str
    inherit_context: bool
    model: str | None
    temperature: float | None
    max_tokens: int | None
    max_tool_iterations: int | None


class ExpertLoader:
    """Load experts from workspace/experts/<name>."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.experts_dir = ensure_dir(get_experts_path(workspace))

    def list_experts(self) -> list[str]:
        """Return all expert directory names under ``workspace/experts``."""
        if not self.experts_dir.exists():
            return []
        return sorted([p.name for p in self.experts_dir.iterdir() if p.is_dir()])

    def load(self, name: str) -> ExpertDef:
        """Load one expert definition from ``workspace/experts/<name>``."""
        expert_dir = self.experts_dir / name
        if not expert_dir.exists():
            raise FileNotFoundError(f"Expert not found: {name}")

        cfg_path = expert_dir / "config.json"
        prompt_path = expert_dir / "EXPERT.md"
        if not cfg_path.exists():
            raise FileNotFoundError(f"Expert config.json missing: {cfg_path}")
        if not prompt_path.exists():
            raise FileNotFoundError(f"Expert EXPERT.md missing: {prompt_path}")

        cfg = self._load_json(cfg_path)
        prompt = prompt_path.read_text(encoding="utf-8").strip()

        tools = cfg.get("tools", {}) or {}
        memory = cfg.get("memory", {}) or {}

        memory_mode = memory.get("mode", "ephemeral")
        if memory_mode not in ("ephemeral", "isolated_long_term"):
            raise ValueError(f"Invalid memory.mode for expert {name}: {memory_mode}")

        inherit_context = bool(memory.get("inherit_context", True))

        return ExpertDef(
            dir_name=name,
            name=cfg.get("name") or name,
            description=cfg.get("description", ""),
            prompt=prompt,
            tools_allow=tools.get("allow"),
            tools_deny=tools.get("deny"),
            memory_mode=memory_mode,
            inherit_context=inherit_context,
            model=cfg.get("model"),
            temperature=cfg.get("temperature"),
            max_tokens=cfg.get("max_tokens"),
            max_tool_iterations=cfg.get("max_tool_iterations"),
        )

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        """Read and parse a JSON file, raising a clear error on invalid JSON."""
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {e}") from e
