"""Expert toolset builder."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
from nanobot.agent.expert.experts import ExpertDef


DEFAULT_TOOL_ORDER = [
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "exec",
    "web_search",
    "web_fetch",
]


def _normalize_list(val: list[str] | None) -> list[str] | None:
    if val is None:
        return None
    return [str(x) for x in val]


def _resolve_path(path: str, workspace: Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = workspace / p
    return p.resolve()


def _is_main_memory_path(path: str, workspace: Path) -> bool:
    target = _resolve_path(path, workspace)
    main_memory = (workspace / "memory").resolve()
    return target == main_memory or main_memory in target.parents


class _ExpertReadFileTool(ReadFileTool):
    def __init__(self, workspace: Path, allowed_dir: Path | None):
        super().__init__(workspace=workspace, allowed_dir=allowed_dir)
        self._workspace = workspace

    async def execute(self, path: str, **kwargs: Any) -> str:
        if _is_main_memory_path(path, self._workspace):
            return "Error: Access to main agent memory path is blocked for expert agents."
        return await super().execute(path=path, **kwargs)


class _ExpertWriteFileTool(WriteFileTool):
    def __init__(self, workspace: Path, allowed_dir: Path | None):
        super().__init__(workspace=workspace, allowed_dir=allowed_dir)
        self._workspace = workspace

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        if _is_main_memory_path(path, self._workspace):
            return "Error: Access to main agent memory path is blocked for expert agents."
        return await super().execute(path=path, content=content, **kwargs)


class _ExpertEditFileTool(EditFileTool):
    def __init__(self, workspace: Path, allowed_dir: Path | None):
        super().__init__(workspace=workspace, allowed_dir=allowed_dir)
        self._workspace = workspace

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        if _is_main_memory_path(path, self._workspace):
            return "Error: Access to main agent memory path is blocked for expert agents."
        return await super().execute(path=path, old_text=old_text, new_text=new_text, **kwargs)


class _ExpertListDirTool(ListDirTool):
    def __init__(self, workspace: Path, allowed_dir: Path | None):
        super().__init__(workspace=workspace, allowed_dir=allowed_dir)
        self._workspace = workspace

    async def execute(self, path: str, **kwargs: Any) -> str:
        if _is_main_memory_path(path, self._workspace):
            return "Error: Access to main agent memory path is blocked for expert agents."
        return await super().execute(path=path, **kwargs)


class _ExpertExecTool(ExecTool):
    def __init__(
        self,
        workspace: Path,
        *,
        timeout: int | None,
        restrict_to_workspace: bool,
    ):
        self._workspace = workspace
        memory_abs = str((workspace / "memory").resolve())
        deny_patterns = [
            rf"(?:^|[\s'\"`])memory/",
            re.escape(memory_abs),
        ]
        super().__init__(
            working_dir=str(workspace),
            timeout=timeout if timeout is not None else 60,
            restrict_to_workspace=restrict_to_workspace,
            deny_patterns=deny_patterns,
        )


def build_expert_tools(
    expert: ExpertDef,
    workspace: Path,
    *,
    brave_api_key: str | None,
    exec_timeout: int | None,
    restrict_to_workspace: bool,
) -> ToolRegistry:
    """Build tool registry for an expert with allow/deny filtering.

    Expert tools must not access main-agent memory paths under ``workspace/memory``.
    """
    tools = ToolRegistry()
    allowed_dir = workspace if restrict_to_workspace else None

    tool_instances = {
        "read_file": _ExpertReadFileTool(workspace=workspace, allowed_dir=allowed_dir),
        "write_file": _ExpertWriteFileTool(workspace=workspace, allowed_dir=allowed_dir),
        "edit_file": _ExpertEditFileTool(workspace=workspace, allowed_dir=allowed_dir),
        "list_dir": _ExpertListDirTool(workspace=workspace, allowed_dir=allowed_dir),
        "exec": _ExpertExecTool(
            workspace=workspace,
            timeout=exec_timeout,
            restrict_to_workspace=restrict_to_workspace,
        ),
        "web_search": WebSearchTool(api_key=brave_api_key),
        "web_fetch": WebFetchTool(),
    }

    allow = _normalize_list(expert.tools_allow)
    deny = set(_normalize_list(expert.tools_deny) or [])

    if allow is None:
        allow = DEFAULT_TOOL_ORDER.copy()

    for name in allow:
        if name in deny:
            continue
        tool = tool_instances.get(name)
        if tool is not None:
            tools.register(tool)

    return tools
