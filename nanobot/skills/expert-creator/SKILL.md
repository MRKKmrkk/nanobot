---
name: expert-creator
description: Create or update expert agents under workspace/experts with focused prompts, tool allow/deny rules, and memory mode configuration.
---

# Expert Creator

Use this skill when the user asks to create or update an expert agent.

## Expert Layout

Each expert lives at:

`experts/<expert-name>/`

Required files:

1. `config.json`
2. `EXPERT.md`

## Required Config Fields

Write `config.json` with:

- `name`: expert name
- `description`: one-sentence purpose
- `tools.allow`: list of tool names (or `null` for defaults)
- `tools.deny`: list of blocked tools (or `null`)
- `memory.mode`: one of:
- `ephemeral` (no persistence)
- `isolated_long_term` (expert-only memory/session persistence)
- `memory.inherit_context`: bool (inherit main session context)

## Creation Workflow

1. Create `experts/<expert-name>/`.
2. Write `EXPERT.md` with identity, scope, and guardrails.
3. Write `config.json` with explicit tool and memory choices.
4. If `tools.allow` is omitted, mention expert will use default tool set.
5. Keep prompt concise and role-specific.

## Update Workflow

1. Read current `config.json` and `EXPERT.md`.
2. Apply only requested changes.
3. Preserve unchanged fields.
4. Validate `memory.mode` is one of supported values.

## Validation Checklist

- Folder exists at `experts/<expert-name>/`
- Both required files exist
- JSON parses correctly
- `memory.mode` is valid
- `EXPERT.md` does not conflict with requested role
