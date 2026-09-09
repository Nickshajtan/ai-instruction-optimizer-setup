---
name: "ai-doc-documentation-authoring"
description: "Write or update ai-doc repository documentation with beginner-friendly explanations, correct public-contract boundaries, and clear routing between guides, operations, and design docs."
version: 1
---

# ai-doc Documentation Authoring

Use this skill when creating or editing documentation for this repository.

## Required Context

Read `docs/AGENTS.md` first for the general documentation-writing standards that human
maintainers can also follow.

## Documentation Groups

- Use `docs/guides/` for user-facing how-to material and configuration examples.
- Use `docs/operations/` for runbooks, packaging, release, and verification procedures.
- Use `docs/design/` for architecture, decisions, and deferred work.
- Use `docs/standards.md` for normative project standards that apply across the repository.

## Agent Routing

This skill is the source of truth for shared repository documentation-writing guidance.
Keep human-facing documentation focused on product usage, architecture, operations, and
public contracts.

- Use `.codex/skills/documentation-authoring/SKILL.md` only for Codex-specific routing.
- Use `.claude/skills/documentation-authoring/SKILL.md` only for Claude-specific routing.
- Use `docs/AGENTS.md` for concise, human-readable documentation-writing guidance that
  people can apply manually.
- Use `docs/CLAUDE.md` only as docs-scoped Claude routing.
- Do not duplicate agent-only workflow instructions in README, guides, runbooks, or
  architecture docs.

## Validation

After documentation changes, run:

```powershell
.\.venv\Scripts\python.exe -m ai_doc check . --format json --non-interactive
```

For repository changes, also run the verification commands required by root `AGENTS.md`.
