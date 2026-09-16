# Multi-Agent Example

Use this example to see how one repository can expose instructions for several coding
agent ecosystems without treating runtime providers as the same concept.

## What It Demonstrates

- Generic persistent instructions in `AGENTS.md`.
- Claude-specific persistent instructions in `CLAUDE.md`.
- Gemini-specific persistent instructions in `GEMINI.md`.
- GitHub Copilot repository-wide and path-specific instructions.
- Codex, Claude, Gemini, and interoperable workspace skills.
- Cursor native rules as Markdown-with-frontmatter `.mdc` files.

## Run

```bash
ai-doc check examples/multi-agent
```

## Expected Result

`ai-doc` discovers and classifies the files as instruction or skill documents. This does
not add Claude, Gemini, Copilot, Cursor, or Codex SDK integrations to the core.

## Evidence Tier

A0 deterministic discovery and static analysis.

## Network Or Model Access

None.
