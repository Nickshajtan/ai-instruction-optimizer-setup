# Benchmark corpus

This directory is reserved for empirical repository-to-agent evidence. It is deliberately separate from `examples/`, which contains synthetic contract fixtures.

## Corpus target

A release-quality benchmark should contain 10-20 real or realistically preserved repository snapshots and 5-10 representative engineering tasks per repository. Each task must identify the repository revision, task text, verification oracle/rubric, instruction baseline, optimized candidate, agent/provider/model version, and repeated raw runs.

## Evidence

Place publishable evidence JSON under `benchmarks/evidence/`. The `Benchmark evidence` workflow evaluates every committed JSON file and fails only for a meaningful task-success regression that clears the configured confidence threshold. Inconclusive evidence does not fail CI.

Do not copy the synthetic file from `examples/benchmark/` here and call it empirical evidence. Results belong here only after the underlying agent runs actually happened.

## Scenario coverage

The corpus should include at least these repository shapes:

- small single-package repository;
- monorepo with nested instructions;
- repository with conflicting or duplicated AI instructions;
- repository with large always-loaded instructions;
- repository using agent-specific overlays such as `AGENTS.md`, `CLAUDE.md`, or `.codex/` routing.

Start with one agent/model to establish repeatability before widening to Codex, Claude, Copilot, or other adapters.

## Case studies

For each publishable benchmark slice, add a case study from `docs/case-studies/TEMPLATE.md`. Report raw run count and uncertainty alongside percentages; never publish fabricated or single-run benchmark claims as proof.
