# Execution Probes

C2 adds real target-agent execution evidence on top of C1 planning observations.

```text
A0 deterministic/static
A1 local semantic ML
B  predictive semantic judgment
C1 real target planning
C2 real target execution
C3 repeated execution benchmark (not current architecture)
```

## Safety Boundary

`ai-doc execute` never points the target command at the source repository. For each evaluation scenario it creates a temporary filesystem copy, invokes the configured target adapter with that copy as its working directory, records the result, measures the filesystem before/after delta, and deletes the temporary copy afterwards.

This is **workspace isolation**, not an OS security sandbox. The adapter process is trusted: it can still access the host according to the operating system permissions of the caller. Container/VM isolation is a future adapter/deployment concern, not something the core CLI pretends to guarantee.

Symlink-containing source trees are rejected by the default workspace copier because a symlink can point outside the temporary tree and undermine the filesystem-isolation claim.

## Command Contract

C2 reuses `AI_DOC_TARGET_COMMAND`; the adapter distinguishes the request by `mode`.

```bash
export AI_DOC_TARGET_COMMAND='your-target-adapter'
ai-doc execute .
```

For C2 the request uses:

```json
{
  "mode": "execute",
  "scenario": {"id": "example", "task": "..."},
  "instructions": [{"path": "AGENTS.md", "text": "..."}]
}
```

The command runs with `cwd` set to the temporary repository copy and returns a normalized execution observation:

```json
{
  "target": "codex",
  "model": "gpt-example",
  "model_version": "2026-09",
  "status": "succeeded",
  "performed_actions": ["Updated the source type", "Ran the relevant test"],
  "forbidden_actions_avoided": ["Edited generated output directly"],
  "reported_checks": ["pytest tests/unit/test_types.py"],
  "uncertainties": [],
  "usage": {
    "input_tokens": 2400,
    "output_tokens": 600,
    "cost_usd": "0.02",
    "latency_ms": 8000
  }
}
```

`ai-doc` does not trust the adapter for filesystem-change reporting. It computes `created_paths`, `modified_paths`, and `deleted_paths` independently from SHA-256 manifests of the temporary workspace.

## Behavioral Verification

C2 reuses the scenario `behavior.required` and `behavior.forbidden` action contract introduced for C1, but verifies it against **performed** actions rather than planned actions.

Exact action matching is always available. Optional local NLI can recognize semantically equivalent wording. NLI remains a verifier of target evidence, never a substitute target.

A target-reported `status: succeeded` is useful metadata, but it is not by itself proof that tests passed or that the task is correct. C2 currently combines real execution, action evidence, and independently observed repository delta. Stronger independent postcondition/test verification can be added without changing the provider-neutral target contract.

## FinOps

C2 performs one target execution per configured scenario. It does not repeat executions automatically. Repeated runs and statistical confidence are intentionally outside the current architecture because they multiply target cost and latency.

## Relationship To The Old Benchmark PR

C2 produces the raw observations that any later statistical layer would need. That makes a separate generic benchmark/evidence framework much less valuable. The preferred direction is to keep execution observations as the source of truth and add only the small amount of repetition/pairing/statistics that proves necessary later, rather than merge a second parallel evidence model now.
