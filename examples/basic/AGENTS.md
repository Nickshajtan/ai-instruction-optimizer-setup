# Agent Instructions

## Core Rules

- MUST run relevant validation before completion.
- NEVER modify generated files.
- Prefer module-local instructions when they exist.
- Prefer module-local instructions when they exist.
- Use best practices for code changes.

## Testing Examples

The following examples are intentionally verbose so the optimizer has a safe extraction
target. When a unit test fails, inspect the smallest relevant module first, read any
module-local test notes, run only the failing test, then expand validation after the fix.

Example A: a frontend component has a failing snapshot. Read the component notes, update
the component behavior, run the component test, and then run the closest affected suite.

Example B: a backend service has a failing unit test. Read the service notes, identify the
contract under test, patch the smallest implementation area, and run the service unit test.

Example C: documentation changed. Run Markdown-oriented checks when configured and avoid
changing generated output unless a maintainer explicitly asks for regeneration.

Example D: if validation commands are not obvious, route to the testing reference and
choose the narrowest documented command before broadening scope.

## Routing

When changing tests, read [testing reference](docs/testing.md).
