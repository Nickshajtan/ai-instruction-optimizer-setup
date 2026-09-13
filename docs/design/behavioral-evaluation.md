# Behavioral Evaluation

`ai-doc` uses C-tier evidence only when it observes behavior produced by a real target model. C is intentionally separate from A static analysis and B predictive judgment.

The first C implementation is a **planning probe**. It asks the configured target model to interpret a real evaluation scenario and repository instruction context, but it does not allow `ai-doc` to execute tools, modify the repository, or claim end-to-end task success.

## Evidence Ladder

```text
A0  deterministic static analysis
A1  local semantic ML
B   predictive semantic judgment
C1  real target planning probe
C2  real target execution          (future)
C3  repeated target benchmark      (future)
```

A1 can verify semantic relationships in text. B can predict whether one instruction set is likely better than another. C1 records what the actual configured target says it intends to do for a concrete task.

A planning probe is therefore stronger evidence than a generic judge, but weaker evidence than executing the task. A compliant plan is not proof that the agent will execute the plan correctly.

## Why There Is No Local Generative Surrogate

`ai-doc` deliberately does not bundle Qwen, SmolLM, or another local generative model as a C-tier surrogate. A local generator adds a large runtime/model artifact while still providing weaker external validity than calling the actual target model.

Local ML remains focused on lightweight A1 capabilities such as embeddings and NLI. When C evidence is requested, the target itself should be observed.

## Command Contract

Planning probes are provider-neutral. Configure:

```bash
export AI_DOC_TARGET_COMMAND='your-target-adapter --plan'
```

Then run:

```bash
ai-doc probe .
```

`ai-doc` starts the command with `shell=False`, writes one JSON request to stdin per evaluation scenario, and expects one JSON response on stdout.

The request shape is:

```json
{
  "mode": "plan",
  "scenario": {
    "id": "generated-schema",
    "profile": "generic",
    "task": "Update API types and regenerate the schema",
    "expected_required": ["Run npm run build-schema"],
    "expected_forbidden": ["Edit generated schema files directly"],
    "tags": []
  },
  "instructions": [
    {
      "path": "AGENTS.md",
      "text": "..."
    }
  ]
}
```

The command returns:

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

Provider authentication, API invocation, and target-specific request formatting belong to the adapter command. This keeps the stable `ai-doc` contract independent of Codex, Claude, or another provider.

## Context Selection

Each scenario uses the existing deterministic context selector. Instruction and skill documents are loaded according to the same task-routing approximation used by semantic evaluation rather than blindly sending every discovered document.

The selected paths are recorded in `BehavioralObservation.context_paths` so evidence can be audited later.

## Verification

The target response is evidence; it is not trusted as its own judge.

`ai-doc` checks scenario expectations against the observed plan:

- required actions can be marked `satisfied` when the plan contains an exact or semantically entailing action;
- forbidden actions are `violated` when the plan proposes an exact or semantically entailing forbidden action;
- a forbidden action explicitly listed in `forbidden_actions_avoided` can be marked `satisfied`;
- otherwise the result is `uncertain`.

Exact checks are always available. If A1 local NLI is enabled and its model is locally available, NLI can verify semantically equivalent wording. Missing NLI never invalidates or discards the target observation; it only reduces verification strength.

NLI is a verifier here, not a replacement for the target model.

## Baseline And Candidate

A single tree can be probed with:

```bash
ai-doc probe .
```

An alternate documentation tree can be compared with:

```bash
ai-doc probe . --candidate /path/to/candidate-tree
```

The same target adapter and evaluation suite are used for both trees. The comparison reports scenario-level counts of satisfied expectations and violations. It deliberately does not create a magic aggregate performance score.

## Cache Identity

Every observation receives a deterministic SHA-256 `cache_key` derived from:

- target name;
- model and model version returned by the adapter;
- probe mode;
- evaluation scenario;
- selected document paths and contents.

This makes observations safe to persist or reuse later when all behavior-affecting inputs are identical. The first C1 implementation exposes the identity but does not add a persistent cache backend.

## FinOps Boundary

C1 performs exactly one target call per evaluation scenario and documentation tree. There are no automatic repetitions.

Typical escalation should be:

```text
ordinary docs/skills
  A0 + A1 + B

important instruction change
  A0 + A1 + B + C1

critical root/security/release instructions
  C1 -> future C2 execution -> future C3 repeated benchmark
```

Repeated target runs belong to C3 and should be reserved for documentation where stronger statistical evidence justifies the cost.

## Non-Goals Of C1

C1 does not:

- execute shell commands or tools;
- modify repository files;
- verify generated code or test results;
- claim task completion;
- estimate a task-success probability;
- repeat stochastic runs;
- replace future sandbox execution benchmarks.

Those boundaries keep planning probes cheap enough to use selectively while preserving an honest distinction between intent and execution.
