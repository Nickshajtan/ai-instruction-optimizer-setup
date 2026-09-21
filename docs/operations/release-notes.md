h# Release Notes

Use this page to identify user-visible behavior and public contract changes for each
`ai-doc` release. It is the canonical release-history document for downstream vendoring
decisions.

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
- Added an explicit-config observability warning when a `--config` run has observation
  logging disabled or omitted.
- Clarified that optimizer-owned output exclusion is an optimizer input-ownership
  boundary, not an unconditional global Markdown discovery exclusion.
- Clarified that project-specific clarity false positives belong in `FindingAdapter`
  extensions rather than organization-specific core analyzer policy.
- Clarified that `loading.mode: on_demand` models context-loading cost and does not imply
  independent runtime discoverability; `SKILL` orphan behavior remains intentional.
