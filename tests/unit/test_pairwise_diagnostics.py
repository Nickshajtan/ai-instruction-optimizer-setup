from ai_doc.cli.optimize import _warn_pairwise_not_performed


def test_optional_zero_performed_with_intentional_skip_reports_only_facts(capsys) -> None:
    _warn_pairwise_not_performed(required=False, skipped_not_needed=2)

    stderr = capsys.readouterr().err
    assert "Pairwise semantic judging was requested but no comparison was performed:" in stderr
    assert "2 candidate(s) already had sufficient non-pairwise objective evidence." in stderr
    assert "Other candidates may not have reached optional pairwise judging." in stderr
    assert "No optional pairwise semantic judgment was needed for this run." not in stderr
    assert "This run did NOT receive a pairwise semantic judgment." not in stderr


def test_mixed_zero_performed_skip_does_not_make_whole_run_claim(capsys) -> None:
    _warn_pairwise_not_performed(required=False, skipped_not_needed=1)

    stderr = capsys.readouterr().err
    assert "1 candidate(s) already had sufficient non-pairwise objective evidence." in stderr
    assert "Other candidates may not have reached optional pairwise judging." in stderr
    assert "No optional pairwise semantic judgment was needed for this run." not in stderr


def test_optional_zero_performed_without_intentional_skip_preserves_warning(capsys) -> None:
    _warn_pairwise_not_performed(required=False, skipped_not_needed=0)

    stderr = capsys.readouterr().err
    assert "Pairwise semantic judging was requested but no comparison was performed:" in stderr
    assert "0 candidates reached the B-tier after earlier gates." in stderr
    assert "This run did NOT receive a pairwise semantic judgment." in stderr


def test_required_zero_performed_preserves_strict_warning(capsys) -> None:
    _warn_pairwise_not_performed(required=True, skipped_not_needed=1)

    stderr = capsys.readouterr().err
    assert "Required pairwise semantic judging was not performed:" in stderr
    assert "0 candidates reached the B-tier after earlier gates." in stderr
    assert "This run did NOT receive a pairwise semantic judgment." in stderr
