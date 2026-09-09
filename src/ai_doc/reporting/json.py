from __future__ import annotations

from pydantic import BaseModel


def render_json(report: BaseModel) -> str:
    return report.model_dump_json(indent=2)
