from __future__ import annotations

import pytest

from tools.minimum_constraints import minimum_constraints


def test_minimum_constraints_parse_plain_requirement() -> None:
    assert minimum_constraints(["package>=1.2"]) == ["package==1.2"]


def test_minimum_constraints_parse_requirement_with_extra() -> None:
    assert minimum_constraints(["package[extra]>=1.2"]) == ["package==1.2"]


def test_minimum_constraints_preserve_marker() -> None:
    assert minimum_constraints(['Package_Name>=1.2; python_version >= "3.12"']) == [
        'package-name==1.2; python_version >= "3.12"'
    ]


def test_minimum_constraints_fail_without_usable_lower_bound() -> None:
    with pytest.raises(ValueError, match="Cannot derive a minimum version"):
        minimum_constraints(["package<2"])
