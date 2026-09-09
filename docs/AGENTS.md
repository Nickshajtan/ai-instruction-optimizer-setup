# Documentation Instructions

These instructions apply to files under `docs/`.

They are intentionally readable as normal project documentation so a person can apply the
same documentation standards manually. Agent-specific workflow instructions live in
skills.

## Audience

Write documentation for users who may not know this project, Promptfoo, DeepEval, Typer,
Pydantic, PyInstaller, or the internal package layout. Prefer a short explanation before
specialized terms, commands, schemas, or architecture rules.

## Writing Rules

- Start each document with what the page is for and when to use it.
- Explain prerequisites before commands.
- Define project-specific terms before relying on them.
- Prefer task-oriented headings over internal implementation labels when the document is
  user-facing.
- Keep command examples copy-pasteable and state where to run them.
- Say when behavior is optional, external, provider-backed, network-backed, or mutates an
  environment.
- Link to deeper documents instead of repeating long details.
- Keep speculative ideas out of API pages; place them in `docs/design/deferred.md`.

## Technical Accuracy

- Do not soften normative standards in [standards.md](standards.md).
- Do not imply that `ai-doc optimize` mutates source Markdown files automatically.
- Do not imply that static `ai-doc check` needs Promptfoo, DeepEval, API keys, or target
  project dependencies.
- Keep public contracts aligned with [../README.md](../README.md) and
  [standards.md](standards.md).
- Keep Extension API docs limited to supported static analyzer extensions.
- Keep model-specific pricing optional and user-supplied; static token budgets are
  model-agnostic guardrails.

## Agent Skills

Agents should load the relevant skill before making documentation, packaging, extension,
or release-process changes:

- [documentation authoring](../.ai/skills/documentation-authoring/SKILL.md)
- [packaging maintenance](../.ai/skills/packaging-maintenance/SKILL.md)
- [extension API maintenance](../.ai/skills/extension-api-maintenance/SKILL.md)
- [verification maintenance](../.ai/skills/verification-maintenance/SKILL.md)
