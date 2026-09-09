# Documentation Instructions

These instructions apply to files under `docs/`.

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
- Say when behavior is optional, external, provider-backed, or requires network access.
- Link to the deeper document instead of repeating long details.

## Technical Accuracy

- Do not soften normative standards in [standards.md](standards.md).
- Do not imply that `ai-doc optimize` mutates source Markdown files automatically.
- Do not imply that static `ai-doc check` needs Promptfoo, DeepEval, API keys, or target
  project dependencies.
- Keep public contracts aligned with [../README.md](../README.md) and
  [standards.md](standards.md).
