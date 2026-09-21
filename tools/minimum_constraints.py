from __future__ import annotations

import argparse
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

MINIMUM_OPERATORS = {">=", "==", "~="}


def minimum_constraints(requirements: Iterable[str]) -> list[str]:
    return [_minimum_constraint(requirement) for requirement in requirements]


def _minimum_constraint(raw_requirement: str) -> str:
    try:
        requirement = Requirement(raw_requirement)
    except InvalidRequirement as exc:
        raise ValueError(f"Invalid requirement: {raw_requirement}") from exc
    minimum = _minimum_version(requirement, raw_requirement)
    name = canonicalize_name(requirement.name)
    marker = f"; {requirement.marker}" if requirement.marker else ""
    return f"{name}=={minimum}{marker}"


def _minimum_version(requirement: Requirement, raw_requirement: str) -> str:
    candidates: list[tuple[Version, str]] = []
    for specifier in requirement.specifier:
        if specifier.operator not in MINIMUM_OPERATORS:
            continue
        try:
            candidates.append((Version(specifier.version), specifier.version))
        except InvalidVersion as exc:
            raise ValueError(f"Cannot derive a minimum version from: {raw_requirement}") from exc
    if not candidates:
        raise ValueError(f"Cannot derive a minimum version from: {raw_requirement}")
    return max(candidates, key=lambda item: item[0])[1]


def project_requirements(pyproject_path: Path) -> list[str]:
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return [
        *pyproject["project"]["dependencies"],
        *pyproject["project"]["optional-dependencies"]["dev"],
    ]


def write_minimum_constraints(requirements: Iterable[str], output_path: Path) -> None:
    output_path.write_text("\n".join(minimum_constraints(requirements)) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate minimum-version constraints from pyproject dependencies.")
    parser.add_argument("pyproject", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        write_minimum_constraints(project_requirements(args.pyproject), args.output)
    except (KeyError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
