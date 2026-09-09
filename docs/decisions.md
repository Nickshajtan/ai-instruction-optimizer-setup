# Design Decisions

This document records project choices and trade-offs.

Use this page when you want to understand why the project is shaped this way. It is not a
setup guide. Each section states the decision, the reasoning, and the cost of that
decision so future changes can evaluate the same trade-off explicitly.

## Treat ai-doc As A Black-Box Tool

Decision: expose CLI, JSON, configuration, and extension contracts as the primary public
interfaces.

Reasoning: target repositories may be PHP, Node.js, Go, .NET, Java, Python, or another
stack. They should not need to adopt Python dependency management to use documentation
analysis.

Trade-off: advanced integrations should use JSON or extensions instead of importing
internal Python modules.

## Keep Core Static Mode Dependency-Light

Decision: static `check` works without Promptfoo, DeepEval, model providers, or API keys.

Reasoning: local and CI checks should be cheap and reliable.

Trade-off: deterministic heuristics cannot prove semantic ambiguity. Semantic behavior
belongs in external evaluation tiers.

## Use Structural Markdown Parsing

Decision: use `markdown-it-py` rather than regex-only parsing.

Reasoning: headings, sections, fenced code, and links need structural treatment for
stable analysis and graph construction.

Trade-off: some heuristics still inspect text inside parsed sections, but discovery and
sectioning are not purely ad hoc.

## Use Pydantic Schemas

Decision: use Pydantic v2 models for configuration, reports, proposals, and optimization
state.

Reasoning: CLI JSON output and extension APIs need stable, validated shapes.

Trade-off: schema changes must be deliberate because JSON consumers may depend on them.

## Isolate External Evaluators

Decision: Promptfoo and DeepEval are adapter implementations, not domain dependencies.

Reasoning: Promptfoo is Node-based and DeepEval APIs can evolve. The core domain should
not expose evaluator-specific result structures.

Trade-off: adapters perform translation work and may support only the normalized feature
set needed by the current release.

## Use Pareto Selection For Optimization

Decision: use Pareto dominance instead of a weighted composite score.

Reasoning: clarity, reliability, invariant recall, and context cost are distinct
objectives. A single score can hide unacceptable behavior regressions.

Trade-off: reports may expose multiple valid candidates, and recommendation is a separate
policy decision.

## Use Explicit Project-Local Extensions

Decision: extensions are loaded from `.ai-doc.yaml` entries and register explicitly.

Reasoning: extension loading executes code, so implicit scanning is a security and
debuggability risk.

Trade-off: users must configure extensions intentionally.

## Use PyInstaller For Executables

Decision: use PyInstaller for standalone executable packaging.

Reasoning: it supports native one-file and one-directory builds, works with Typer and
Pydantic, bundles the Python interpreter, supports package data collection, and is
debuggable with `--onedir`.

Trade-off: builds must be produced on native OS runners. Cross-compilation is not
supported.

## Keep Promptfoo Node-Backed But Python-Installable

Decision: expose Promptfoo through Python optional dependencies and setup commands, but do
not bundle Promptfoo or Node.

Reasoning: current Promptfoo is TypeScript/Node-based, while its PyPI package provides a
Python-managed wrapper. Installing the wrapper through `ai-doc` improves setup ergonomics
without hiding the Node runtime requirement. Static analysis should remain independent of
deep evaluation tooling.

Trade-off: `check --deep --install-missing` can install Python packages, but users still
need Node.js when Promptfoo is selected.
