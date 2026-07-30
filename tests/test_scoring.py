from app.tracker.scoring import compute_eu_alignment_score


def test_eu_domiciled_and_available_scores_highest_tier() -> None:
    score, tier = compute_eu_alignment_score("eu_domiciled", "available")
    assert score == 100
    assert tier == "Strong EU alignment"


def test_non_eu_domiciled_and_not_available_scores_lowest_tier() -> None:
    score, tier = compute_eu_alignment_score("non_eu_domiciled", "not_available")
    assert score == 0
    assert tier == "Low EU alignment"


def test_unclear_on_both_dimensions_is_flagged_as_insufficient_data_not_a_confirmed_weakness() -> None:
    # No confidence boost or penalty when we genuinely don't know - and
    # crucially, this must read as "no evidence yet," not as a confirmed
    # weak vendor (which the raw score alone would otherwise imply).
    score, tier = compute_eu_alignment_score("unclear", "unclear")
    assert score == 30
    assert tier == "Insufficient data"


def test_one_resolved_signal_still_gets_a_normal_tier_even_if_the_other_is_unclear() -> None:
    score, tier = compute_eu_alignment_score("unclear", "selectable")
    assert score == 45
    assert tier == "Weak EU alignment"


def test_conflicting_domicile_gets_its_own_tier_regardless_of_residency_status() -> None:
    # Contradictory evidence is a real finding, not something that should
    # quietly land in "Weak"/"Insufficient data" alongside a plain absence
    # of evidence.
    score, tier = compute_eu_alignment_score("conflicting", "available")
    assert tier == "Conflicting evidence"
    score, tier = compute_eu_alignment_score("conflicting", "unclear")
    assert tier == "Conflicting evidence"


def test_eu_domiciled_company_outscores_non_eu_company_even_with_identical_hosting() -> None:
    eu_score, _ = compute_eu_alignment_score("eu_domiciled", "selectable")
    non_eu_score, _ = compute_eu_alignment_score("non_eu_domiciled", "selectable")
    assert eu_score > non_eu_score


def test_unknown_status_strings_fall_back_to_neutral_points() -> None:
    score, _ = compute_eu_alignment_score("some_future_status", "another_future_status")
    assert score == 30
