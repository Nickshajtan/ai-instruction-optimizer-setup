from pathlib import Path

from ai_doc.ml.model_paths import MODEL_ROOT_ENV, NLI_MODEL_SLOT, SIMILARITY_MODEL_SLOT, resolve_local_model_reference


def test_explicit_model_path_wins(tmp_path: Path, monkeypatch) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    configured = tmp_path / "configured"
    (configured / SIMILARITY_MODEL_SLOT).mkdir(parents=True)
    monkeypatch.setenv(MODEL_ROOT_ENV, str(configured))

    resolved = resolve_local_model_reference(str(explicit), SIMILARITY_MODEL_SLOT)

    assert resolved == str(explicit.resolve())


def test_model_root_env_resolves_slot_directory(tmp_path: Path, monkeypatch) -> None:
    model_root = tmp_path / "models"
    nli = model_root / NLI_MODEL_SLOT
    nli.mkdir(parents=True)
    monkeypatch.setenv(MODEL_ROOT_ENV, str(model_root))

    resolved = resolve_local_model_reference("cross-encoder/example", NLI_MODEL_SLOT)

    assert resolved == str(nli.resolve())


def test_unresolved_reference_is_left_for_local_cache_lookup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(MODEL_ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    resolved = resolve_local_model_reference("sentence-transformers/example", SIMILARITY_MODEL_SLOT)

    assert resolved == "sentence-transformers/example"
