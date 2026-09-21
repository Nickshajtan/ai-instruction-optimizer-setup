# Behavioral Evaluation

`ai-doc` uses C-tier evidence only when it observes behavior produced by a real target model. C is intentionally separate from A static analysis and B predictive judgment.

The C implementation has two current layers. C1 planning probes ask the configured target model to interpret a real evaluation scenario and repository instruction context without allowing repository mutation. C2 execution probes run a trusted target adapter in an isolated workspace copy and record the resulting actions and filesystem delta.

## Evidence Ladder

```text
A0  deterministic static analysis
A1  local semantic ML
B   predictive semantic judgment
C1  real target planning probe
C2  real target execution
C3  repeated target benchmark      (not current architecture)
```

A1 can verify semantic relationships in text. B can predict whether one instruction set is likely better than another. C1 records what the actual configured target says it intends to do for a concrete task. C2 records what the target reports doing and what changed in the temporary workspace. A compliant plan is stronger evidence than a generic judge, but it is not proof of correct execution; that is why C2 exists.

## Why There Is No Local Generative Surrogate

`ai-doc` deliberately does not bundle Qwen, SmolLM, or another local generative model as a C-tier surrogate. That adds a large runtime/model artifact while still providing weaker external validity than calling the actual target model.

Local ML stays focused on lightweight A1 capabilities such as embeddings and NLI. When C evidence is requested, the target itself should be observed.

## Scenario Contract

B and C deliberately use different expectation fields. Existing `expected.required` / `expected.forbidden` describe semantic requirements that documentation should preserve. They are not necessarily actions; a semantic requirement such as `NEVER modify generated files` must not be misread as an action the target should plan.

C1 therefore uses a separate `behavior` block:

```yaml
id: generated-schema
profile: coding-task
task: Update API types and regenerate the schema
expected:
  required:
    - NEVER edit generated schema files directly.
behavior:
  required:
    - run npm run build-schema
  forbidden:
    - edit generated schema files directly
```

The semantic `expected` block remains available to B/evaluator integrations. The behavioral block is the action contract used to verify C observations.

## Command Contract

Planning probes are provider-neutral. The operator authorizes C-tier target probing by
choosing to run `ai-doc probe` and by providing `AI_DOC_TARGET_COMMAND`; repository
content cannot configure that command for itself. Configure:

```bash
export AI_DOC_TARGET_COMMAND='your-target-adapter --plan'
ai-doc probe .
```

`ai-doc` starts the command with `shell=False`, writes one JSON request to stdin per evaluation scenario, and expects one JSON response on stdout.

The request contains the complete scenario and task-selected instruction context:

```json
{
  "mode": "plan",
  "scenario": {
    "id": "generated-schema",
    "profile": "coding-task",
    "task": "Update API types and regenerate the schema",
    "expected_required": ["NEVER edit generated schema files directly."],
    "expected_forbidden": [],
    "behavior_required": ["run npm run build-schema"],
    "behavior_forbidden": ["edit generated schema files directly"],
    "tags": []
  },
  "instructions": [
    {"path": "AGENTS.md", "text": "..."}
  ]
}
```

The command returns a normalized planning observation:

```json
{
  "target": "codex",
  "model": "gpt-example",
  "model_version": "2026-09",
  "applicable_rules": ["Regenerate generated schema through the build command"],
  "planned_actions": ["Change API source types", "Run npm run build-schema"],
  "forbidden_actions_avoided": ["Edit generated schema files directly"],
  "uncertainties": [],
  "usage": {
    "input_tokens": 1200,
    "output_tokens": 180,
    "cost_usd": "0.004",
    "latency_ms": 900
  },
  "raw_summary": {}
}
```

Provider authentication, API invocation, and Codex/Claude-specific formatting belong to the adapter command. The stable `ai-doc` contract stays provider-neutral.
The adapter command runs with the caller's normal OS authority and environment unless the
operator's wrapper constrains it. C1 sends repository-controlled scenario text and
selected documentation to the command but does not grant repository configuration a way
to choose the command.

## Context Selection

Each scenario uses the existing deterministic context selector. Instruction and skill documents are loaded according to the same task-routing approximation used by semantic evaluation rather than blindly sending every discovered document.

Selected paths are recorded in `BehavioralObservation.context_paths` so evidence can be audited later.

## Verification

The target response is evidence; it is not trusted as its own judge. `ai-doc` checks the scenario's `behavior` contract against the observed plan:

- a required action is `satisfied` when the plan contains an exact or semantically entailing action;
- a forbidden action is `violated` when the plan proposes an exact or semantically entailing action;
- a forbidden action explicitly reported in `forbidden_actions_avoided` can be `satisfied`;
- otherwise the result is `uncertain`.

Exact checks are always available. If A1 local NLI is enabled and its model is locally available, NLI can verify semantically equivalent wording. Missing NLI never invalidates or discards the target observation; verification simply falls back to exact evidence and uncertainty.

NLI is a verifier here, not a replacement for the target model.

## Baseline And Candidate

Probe one tree:

```bash
ai-doc probe .
```

Compare an alternate documentation tree:

```bash
ai-doc probe . --candidate /path/to/candidate-tree
```

The same target adapter and evaluation suite are used for both trees. The comparison reports scenario-level satisfied/violation counts and deliberately avoids a magic aggregate performance score.

## Cache Identity

Every observation receives a deterministic SHA-256 `cache_key` derived from target name, model/version, probe mode, scenario, and selected document paths/contents. This identity is safe to use for persistent evidence reuse when all behavior-affecting inputs are identical. C1 exposes the identity but does not yet add a persistent cache backend.

## FinOps Boundary

C1 performs exactly one target call per evaluation scenario and documentation tree. There are no automatic repetitions.

```text
ordinary docs/skills
  A0 + A1 + B

important instruction change
  A0 + A1 + B + C1

critical root/security/release instructions
  C1 -> C2 execution
```

Repeated target runs are intentionally outside the current architecture and should be reserved for a separate design only when stronger statistical evidence justifies the cost.

## Execution Trust Boundary

C2 execution uses the same operator-selected `AI_DOC_TARGET_COMMAND` but sends
`mode: execute` and runs the command with `cwd` set to a temporary workspace copy.
Invoking `ai-doc execute` is the explicit operator action that authorizes real target
execution for the configured command. The workspace copy protects the source repository
from direct mutation, but it is not an OS sandbox: the target process still has the
normal OS authority, ambient environment, network access, and user-level configuration
available to the caller unless the operator's wrapper restricts them.

Repository-controlled scenarios and documentation are untrusted input to that command.
They can influence what the target is asked to plan or execute, but they do not select
the target executable. Use a trusted wrapper when the target agent needs credentials or
when host access must be narrowed.

## Non-Goals Of C1

C1 does not execute shell commands or tools, modify repository files, verify generated code/tests, claim task completion, estimate task-success probability, or repeat stochastic runs. C2 covers real target execution in an isolated workspace copy. Repeated stochastic runs remain outside the current architecture.
