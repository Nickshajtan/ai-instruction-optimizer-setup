# Release Notes

Use this page to identify user-visible behavior and public contract changes for each
`ai-doc` release. It is the canonical release-history document for downstream vendoring
decisions.

## 0.2.1

This patch release closes release-readiness gaps while preserving existing default
behavior.

- Added explicit Promptfoo `model_graded` evaluation mode with generated `llm-rubric`
  assertions from `EvaluationScenario` requirements.
- Preserved Promptfoo lexical `echo` plus `contains`/`not-contains` behavior as the
  default for existing `engine: promptfoo` configuration.
- Required explicit model configuration for Promptfoo model-graded evaluation.
- Added `evaluation.deep.budget` for `ai-doc check --deep` request, input-token,
  output-token, and USD limits.
- Recorded completed deep-evaluation usage before blocking later scenario calls after
  budget exhaustion or overrun.
- Marked unknown token and cost usage dimensions as unknown instead of fabricating
  values for Promptfoo, DeepEval, or opaque evaluator backends.
- Updated README and guides to position `ai-doc` as a quality, evidence, and cost
  gateway for AI-facing repository documentation.
- Clarified that static risk findings do not prove agent failure, and that Promptfoo and
  DeepEval are delegated evaluation engines rather than replaced by `ai-doc`.

## 0.2.0

This release hardens static analysis, semantic optimization evidence accounting, and
extension contracts for downstream vendoring.

- Added `STRUCTURE_NO_HEADINGS` for substantial heading-less Markdown documents with
  structured list content.
- Refined duplicate-list reporting so repeated bullets inside a substantial heading-less
  document do not flood reports with derivative `FINOPS_DUPLICATE_LIST_ITEM` findings,
  while cross-document and named-section duplicate findings remain visible.
- Added optional pairwise semantic controls: `--require-pairwise-semantic`,
  `--gated-pairwise`, and `optimization.gated_pairwise`.
- Added pairwise requested, performed, and skipped-not-needed accounting in optimization
  reports and observation records.
- Added `FindingAdapter` as a first-class Python extension capability through
  `registry.add_finding_adapter(...)`.
- Added `--allow-extensions` as the explicit trust gate for repository-declared Python
  and process extensions. Commands now fail closed instead of executing configured
  extensions from an untrusted checkout by default.
- Preserved pre-adaptation built-in error findings as authoritative for the default
  `check` exit code and added finding audit data for adapter suppression or severity
  changes.
- Removed implicit GEPA model defaults. GEPA now requires explicit reflection and
  mutation model configuration when enabled.
- Hardened execution probes so unexplained workspace mutation is reported as
  uncertainty, and symlinks are rejected at the workspace isolation boundary.
- Restricted process-extension environment inheritance to a minimal runtime environment
  plus explicit configured `env:` values.
- Added a dedicated `tests/security` regression suite and GitHub Actions security check.
- Refined CI path filters so security/control-plane Markdown is not blanket-ignored.
- Added normative security engineering standards, security-review skills, Bandit,
  pip-audit, and focused mutation coverage for security-sensitive decision logic.
- Added an explicit-config observability warning when a `--config` run has observation
  logging disabled or omitted.
- Clarified that optimizer-owned output exclusion is an optimizer input-ownership
  boundary, not an unconditional global Markdown discovery exclusion.
- Clarified that project-specific clarity false positives belong in `FindingAdapter`
  extensions rather than organization-specific core analyzer policy.
- Clarified that `loading.mode: on_demand` models context-loading cost and does not imply
  independent runtime discoverability; `SKILL` orphan behavior remains intentional.
