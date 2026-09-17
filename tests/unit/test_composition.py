from __future__ import annotations

import pytest

from ai_doc.composition import register_configured_extensions
from ai_doc.config.models import DEFAULT_CONFIG, CommandExtensionConfig, ExtensionRuntimeConfig
from ai_doc.plugins.registry import ExtensionRegistry


class FakeTokenCounter:
    def count(self, text: str, model: str | None = None) -> int:
        del text, model
        return 1


class FakeEvaluator:
    def evaluate(self, baseline, candidate, suite):
        del baseline, candidate, suite
        return None


class FakePolicy:
    def choose(self, baseline, frontier):
        del baseline, frontier
        return None


class FakeProvider:
    def invoke(self, operation: str, payload: dict[str, object]):
        del operation, payload
        return None


def test_builtin_component_names_cannot_be_replaced_by_existing_registrations(monkeypatch) -> None:
    monkeypatch.setenv("AI_DOC_SEMANTIC_COMMAND", "python fixture.py")
    registry = ExtensionRegistry()
    registry.add_token_counter("approximate", FakeTokenCounter())

    with pytest.raises(ValueError, match="Duplicate token counter registration: approximate"):
        register_configured_extensions(DEFAULT_CONFIG.model_copy(deep=True), registry)


@pytest.mark.parametrize(
    ("kind", "name", "component"),
    [
        ("evaluator", "promptfoo", FakeEvaluator()),
        ("evaluator", "deepeval", FakeEvaluator()),
        ("recommendation_policy", "default", FakePolicy()),
        ("provider", "semantic-command", FakeProvider()),
    ],
)
def test_reserved_builtin_names_fail_deterministically(monkeypatch, kind: str, name: str, component: object) -> None:
    monkeypatch.setenv("AI_DOC_SEMANTIC_COMMAND", "python fixture.py")
    registry = ExtensionRegistry()
    add = getattr(registry, f"add_{kind}")
    add(name, component)

    with pytest.raises(ValueError, match=f"Duplicate .* registration: {name}"):
        register_configured_extensions(DEFAULT_CONFIG.model_copy(deep=True), registry)


def test_process_registration_cannot_replace_existing_python_registration() -> None:
    registry = ExtensionRegistry()
    config = DEFAULT_CONFIG.model_copy(
        deep=True,
        update={
            "extension_runtime": ExtensionRuntimeConfig(
                token_counters={
                    "company": CommandExtensionConfig(command=["python", "counter.py"]),
                }
            )
        },
    )
    registry.add_token_counter("company", FakeTokenCounter())

    with pytest.raises(ValueError, match="Duplicate token counter registration: company"):
        register_configured_extensions(config, registry)
