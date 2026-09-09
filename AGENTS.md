# Agent Instructions

This is the root instruction entry point for AI coding agents working in this repository.
These instructions apply to the whole repository unless a nested instruction file says
otherwise.

## Project Context
`ai-doc` is a Python CLI that analyzes and optimizes Markdown documentation used by AI
coding agents. It must remain reusable across target projects and operating systems.

Start with the [README.md](README.md) Documentation section as the project documentation
map.

## Required Reading
- Use [docs/standards.md](docs/standards.md) for normative coding, API, CLI, testing, and
  documentation rules.
- Use [docs/operations/runbook.md](docs/operations/runbook.md) for operational commands and troubleshooting.
- Use [docs/design/architecture.md](docs/design/architecture.md) before changing module boundaries,
  data flow, public contracts, or adapter responsibilities.
- Use [docs/operations/packaging.md](docs/operations/packaging.md) before changing build, wheel, source-checkout,
  or executable behavior.
- Use [.ai/skills/documentation-authoring/SKILL.md](.ai/skills/documentation-authoring/SKILL.md)
  before changing repository documentation.

## Agent Setup
Shared documentation-authoring instructions live in
[.ai/skills/documentation-authoring/SKILL.md](.ai/skills/documentation-authoring/SKILL.md).
Codex-specific and Claude-specific skill routing lives in `.codex/skills/` and
`.claude/skills/`.

Agent-only implementation workflows belong in skills, not human-facing docs.

## Repository policy:

- Add or update `.ai/skills/` when repeatable agent instructions start appearing in
  human-facing docs.
- Keep `docs/AGENTS.md` as concise, human-readable documentation-writing guidance.
- Keep `docs/CLAUDE.md` as docs-scoped Claude routing.

## Public Contracts

Preserve the public contracts documented in [docs/standards.md](docs/standards.md):
CLI commands, options, exit codes, JSON output schemas, `.ai-doc.yaml`, configured
project-local extensions, and explicit exports from `ai_doc.api.v1`.

Do not document internal optimizer, parser, storage, Promptfoo, DeepEval, or GEPA modules
as extension contracts.

## Implementation Rules

- Prefer the existing architecture and the smallest coherent change.
- Keep static `check` usable without Promptfoo, DeepEval, provider credentials, or
  target-project Python dependencies.
- Do not mutate target repository Markdown files during optimization.
- Keep optional integrations isolated behind the existing adapter boundaries.
- Use `ai_doc.api.v1` in extension examples instead of internal modules.
- Keep package-owned resources loadable from source, wheel, and executable modes.

## Verification

Before completing code changes, run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy
```

For packaging changes, also run the relevant smoke tests from
[docs/operations/testing-and-release.md](docs/operations/testing-and-release.md).

## Documentation
- Update `docs/` when behavior, architecture, packaging, or public contracts change.
- Keep root `README.md`, `ARCHITECTURE.md` as entry points or pointers,
  not competing sources of truth.
