---
name: "ai-doc-extension-api-maintenance"
description: "Maintain ai-doc's public extension API, project-local extension loading, and examples while keeping internals out of public contracts."
version: 1
---

# ai-doc Extension API Maintenance

Use this skill when changing extension loading, `ai_doc.api.v1`, extension examples,
extension configuration, or documentation about public extension contracts.

## Required Context

Read these first:

- `docs/guides/extensions.md`
- `docs/guides/configuration.md`
- `docs/standards.md`

Read `docs/design/architecture.md` before changing package boundaries or public/internal
contracts.

## Instructions

- Treat CLI commands, exit codes, JSON schemas, `.ai-doc.yaml`, configured extensions,
  and explicit `ai_doc.api.v1` exports as public contracts.
- Keep extension examples importing from `ai_doc.api.v1`, not internal modules.
- Load only explicitly configured project-local extensions.
- Keep extension paths inside the project root.
- Use explicit `register(registry)` functions; do not rely on import-time monkey-patching.
- Validate registrations and fail with actionable errors.
- In normal mode, show concise extension diagnostics. In debug mode, include full details.
- Do not document optimizer internals, parser internals, Promptfoo internals, DeepEval
  internals, storage/cache internals, or orchestration internals as extension points.

## Validation

Run targeted extension tests after changes:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_extensions_and_cli.py
```

For public API changes, also run the full repository verification required by
`AGENTS.md`.
