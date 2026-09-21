from __future__ import annotations

from ai_doc.config.models import AiDocConfig

ALLOW_EXTENSIONS_FLAG = "--allow-extensions"


class ExtensionTrustError(RuntimeError):
    pass


def ensure_extensions_authorized(config: AiDocConfig, *, allow_extensions: bool) -> None:
    executable_declarations = configured_executable_extensions(config)
    if allow_extensions or not executable_declarations:
        return
    declarations = "\n".join(f"  - {item}" for item in executable_declarations)
    raise ExtensionTrustError(
        "Executable extensions are configured but were not executed.\n\n"
        "Repository-controlled configuration cannot authorize extension execution.\n"
        f"Rerun with {ALLOW_EXTENSIONS_FLAG} only for a trusted repository.\n\n"
        f"Configured executable extensions:\n{declarations}"
    )


def configured_executable_extensions(config: AiDocConfig) -> list[str]:
    declarations = [f"python:{extension.path}" for extension in config.extensions]
    runtime = config.extension_runtime
    for capability, items in (
        ("analyzer", runtime.analyzers),
        ("evaluator", runtime.evaluators),
        ("token-counter", runtime.token_counters),
        ("recommendation-policy", runtime.recommendation_policies),
        ("semantic-provider", runtime.providers),
    ):
        declarations.extend(f"process:{capability}:{name}" for name in sorted(items))
    return declarations
