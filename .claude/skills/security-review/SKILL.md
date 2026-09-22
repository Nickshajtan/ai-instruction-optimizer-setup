---
name: "ai-doc-security-review"
description: "Thin Claude Code adapter for the shared security review skill."
---

# Claude Security Review Adapter

Claude Code should load
[.ai/skills/security-review/SKILL.md](../../../.ai/skills/security-review/SKILL.md)
before changing trust boundaries, credentials, external providers, filesystem isolation,
extension authority, CI security permissions, or security-relevant verdicts. Keep this
adapter as Claude routing only.
