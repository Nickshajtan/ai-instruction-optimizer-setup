import sys

from ai_doc.config.search import GepaConfig
from ai_doc.optimizer.prompt_suboptimizer import DeepEvalGEPAPromptOptimizer


def test_gepa_boundary_does_not_import_deepeval_at_module_import() -> None:
    assert "deepeval.prompt" not in sys.modules
    optimizer = DeepEvalGEPAPromptOptimizer(GepaConfig(enabled=True, random_seed=123))
    assert optimizer.config.random_seed == 123
