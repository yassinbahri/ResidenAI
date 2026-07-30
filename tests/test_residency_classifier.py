from app.tracker.residency_classifier import classify_eu_eea_residency


def test_classifies_available_when_eu_data_residency_mentioned() -> None:
    result = classify_eu_eea_residency(
        {"privacy-policy": "We offer data residency in Europe for eligible business customers."}
    )
    assert result.status == "available"
    assert result.evidence_quote is not None
    assert "europe" in result.evidence_quote.lower()
    assert result.evidence_source_key == "privacy-policy"


def test_classifies_selectable_when_customer_must_choose() -> None:
    result = classify_eu_eea_residency(
        {"deployment-types": "Customers can choose Europe as their preferred data zone."}
    )
    assert result.status == "selectable"


def test_classifies_not_available_and_it_beats_available() -> None:
    # A page could plausibly mention "Europe" in a way that would also match
    # an availability pattern, but an explicit denial must win - a false
    # "available" claim is worse than missing a subtler positive one.
    result = classify_eu_eea_residency(
        {
            "faq": (
                "Our service is not currently available in the EU. "
                "We hope to add European data residency in the future."
            )
        }
    )
    assert result.status == "not_available"


def test_classifies_unclear_when_no_geography_mentioned() -> None:
    result = classify_eu_eea_residency({"retention-policy": "We delete your data after 30 days."})
    assert result.status == "unclear"
    assert result.evidence_quote is None
    assert result.evidence_source_key is None


def test_classifies_unclear_for_empty_input() -> None:
    result = classify_eu_eea_residency({})
    assert result.status == "unclear"


def test_checks_multiple_sources_and_returns_first_match() -> None:
    result = classify_eu_eea_residency(
        {
            "unrelated-page": "This page says nothing about geography.",
            "residency-page": "Data is processed in the EU for all customers.",
        }
    )
    assert result.status == "available"
    assert result.evidence_source_key == "residency-page"


def test_negated_availability_statement_is_not_misread_as_positive() -> None:
    # Real false positive found via live testing: "Tracing is not currently
    # EU data residency compliant" contains the phrase "EU data residency"
    # but is an explicit denial, not a claim of availability.
    result = classify_eu_eea_residency(
        {"data-controls": "Tracing is not currently EU data residency compliant for the realtime endpoint."}
    )
    assert result.status != "available"


def test_negation_does_not_hide_a_later_genuine_match() -> None:
    result = classify_eu_eea_residency(
        {
            "docs": (
                "Tracing is not currently EU data residency compliant for the realtime endpoint. "
                "However, the main Chat Completions API does offer data residency in Europe for eligible accounts."
            )
        }
    )
    assert result.status == "available"


def test_evidence_quote_includes_surrounding_context() -> None:
    text = "Some preamble text. " + "x" * 50 + " EU region is supported for storage. " + "y" * 50
    result = classify_eu_eea_residency({"docs": text})
    assert result.status == "available"
    assert "EU region" in result.evidence_quote
