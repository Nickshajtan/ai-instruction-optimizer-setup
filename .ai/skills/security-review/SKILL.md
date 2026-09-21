---
name: "security-review"
description: "Review ai-doc changes that modify trust boundaries, security-sensitive decisions, credentials, providers, filesystem isolation, CI permissions, or finding/verdict authority."
version: 1
---

# Security Review

Use this skill before changing code, tests, documentation, or CI that affects a trust
boundary or a security-sensitive decision.

## Activation Criteria

Use this skill for changes involving:

- dynamic Python or module loading;
- subprocesses, external tools, or process protocols;
- extension execution or extension authorization;
- external providers, model selection, or provider-backed behavior;
- environment variables, secrets, or credentials;
- filesystem isolation, temporary workspaces, symlinks, output paths, or writable paths;
- network-capable behavior;
- serialization or deserialization of untrusted input;
- CI permissions, workflow triggers, or security tooling;
- finding, verdict, or safety-evidence suppression;
- agent/provider/process self-report used as evidence;
- repository-controlled configuration granting capabilities.

## Review Model

For each relevant change, answer concretely:

```text
Trust boundary:
Attacker-controlled input:
Privileged operation:
Authorization:
Validation:
Failure mode:
Audit evidence:
Adversarial regression test:
```

Avoid generic statements such as "input is validated" without naming what the validation
prevents and which boundary applies it.

## Required Questions

You must answer these questions before implementation or review sign-off:

- What can an untrusted repository control?
- Does that input reach executable behavior?
- Who authorizes that behavior?
- Can configuration authorize itself?
- Does ambient environment change behavior?
- Are credentials available unnecessarily?
- Does a subprocess inherit more authority than required?
- Can an extension weaken built-in safety evidence?
- Is external self-report being treated as fact?
- Can filesystem links escape intended boundaries?
- Does failure become permissive?
- Can diagnostics leak sensitive information?
- Is there a causal regression test?
- Would mutation of the security predicate survive the test suite?

## Output

For a security-sensitive implementation or review, include a concise section:

```text
Trust boundary:
Untrusted input:
Protected capability:
Authorization:
Validation:
Failure semantics:
Audit evidence:
Regression test:
Residual risk:
```

Do not add this ceremony for ordinary non-security changes.
