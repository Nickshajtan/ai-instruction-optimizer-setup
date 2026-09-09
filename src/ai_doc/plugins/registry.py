from __future__ import annotations

from typing import cast

from ai_doc.analyzers.base import Analyzer


class AnalyzerRegistrationValidator:
    def validate(self, analyzer: object) -> Analyzer:
        analyze = getattr(analyzer, "analyze", None)
        if not callable(analyze):
            raise TypeError("Analyzer registration must provide an object with analyze(context).")
        return cast(Analyzer, analyzer)


class ExtensionRegistry:
    def __init__(self, validator: AnalyzerRegistrationValidator | None = None) -> None:
        self._validator = validator or AnalyzerRegistrationValidator()
        self._analyzers: list[Analyzer] = []

    @property
    def analyzers(self) -> tuple[Analyzer, ...]:
        return tuple(self._analyzers)

    def add_analyzer(self, analyzer: object) -> None:
        self._analyzers.append(self._validator.validate(analyzer))
