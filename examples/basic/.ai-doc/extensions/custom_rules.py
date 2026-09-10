from ai_doc.api.v1 import AnalysisContext, Finding


class ExamplePolicyAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for document in context.snapshot.documents:
            if "generated files" in document.text.lower():
                findings.append(
                    Finding(
                        code="EXAMPLE_GENERATED_FILES_POLICY",
                        category="risk",
                        severity="info",
                        path=document.relative_path,
                        section=None,
                        message="Example extension detected generated-files policy language.",
                        evidence={"extension": "custom_rules.py"},
                        suggestion=None,
                    )
                )
        return findings


def register(registry) -> None:
    registry.add_analyzer(ExamplePolicyAnalyzer())
