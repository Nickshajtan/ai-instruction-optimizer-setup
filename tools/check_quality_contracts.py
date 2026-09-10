"""Repository-specific static checks for misleading implementation patterns."""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path("src")


def _function_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = node.args
    parameters = {argument.arg for argument in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    if args.vararg is not None:
        parameters.add(args.vararg.arg)
    if args.kwarg is not None:
        parameters.add(args.kwarg.arg)
    return parameters


def _deleted_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Delete):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def find_deleted_parameters(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        deleted = _deleted_names(node) & _function_parameters(node)
        for parameter in sorted(deleted):
            findings.append(
                f"{path}:{node.lineno}: {node.name} explicitly deletes parameter {parameter!r}; "
                "implement the contract, remove the parameter, or document a narrow compatibility exception"
            )

    return findings


def main() -> int:
    findings: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        findings.extend(find_deleted_parameters(path))

    if findings:
        print("Quality contract violations:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Quality contract checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
