from __future__ import annotations

from importlib import resources


def read_text_resource(name: str) -> str:
    return resources.files("ai_doc.resources").joinpath(name).read_text(encoding="utf-8")
