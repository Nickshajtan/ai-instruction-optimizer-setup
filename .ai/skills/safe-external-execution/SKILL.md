---
name: "safe-external-execution"
description: "Review ai-doc changes that introduce or materially change subprocesses, dynamic code loading, executable extensions, command-backed providers, or other external execution."
version: 1
---

# Safe External Execution

Use this skill with `security-review` whenever code introduces or materially changes
subprocesses, dynamic Python loading, plugin execution, executable extension protocols,
command-backed providers, external evaluators, execution probes, or other local executable
processes.

## Core Rule

Safe argument passing is not the same problem as safe authorization.

You must review and document external execution as:

```text
authorization
+ executable selection
+ argument construction
+ environment authority
+ working directory
+ filesystem authority
+ network implications
+ timeout/resource behavior
+ output validation
+ failure semantics
```

## Process Checklist

Authorization: identify who is allowed to cause the process to execute and whether
repository-controlled content can independently cross that boundary.

Executable selection: identify whether the executable is fixed by trusted code, selected
by operator configuration, selected by repository configuration, or supplied directly by
untrusted input.

Arguments: use argv-based execution. Avoid shell interpretation unless there is an
explicit reviewed requirement. Never treat `shell=False` as sufficient authorization.

Environment: deliberately choose empty/minimal environment, allowlisted environment,
explicit extension environment, or full inherited environment. Full inheritance requires
specific justification for security-sensitive processes.

Working directory: identify whether the process runs against the project root, an
isolated workspace, a temporary directory, or another explicit path. Do not assume `cwd`
provides filesystem sandboxing.

Filesystem: review read/write capability, output paths, temporary paths, and symlink
behavior.

Network: do not claim network isolation unless it is actually enforced.

Timeout and termination: external processes must retain bounded execution behavior.

Output: treat stdout, stderr, and protocol payloads as untrusted. Validate structured
responses before using them for security-sensitive decisions.

Secrets: do not expose credentials merely because they exist in the parent process.

## Dynamic Python Execution

Apply equivalent reasoning to dynamic module and plugin loading. Path containment does
not imply code trust; executing a contained repository-local Python file is still
arbitrary code execution if the repository is untrusted.
