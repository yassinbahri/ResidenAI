from app.tracker.domicile_classifier import classify_eu_domicile


def test_classifies_eu_domiciled_with_clear_self_reference() -> None:
    result = classify_eu_domicile(
        {"privacy-policy": "We are headquartered in Germany and comply with the GDPR as a data controller."}
    )
    assert result.status == "eu_domiciled"
    assert result.evidence_quote is not None


def test_evidence_char_offsets_point_at_the_actual_match() -> None:
    text = "We are headquartered in Germany and comply with the GDPR as a data controller."
    result = classify_eu_domicile({"privacy-policy": text})
    assert result.evidence_char_start is not None
    assert result.evidence_char_end is not None
    assert text[result.evidence_char_start : result.evidence_char_end] == "headquartered in Germany"


def test_classifies_non_eu_domiciled_with_clear_self_reference() -> None:
    result = classify_eu_domicile(
        {"terms": "Acme Inc. is a Delaware corporation. We are headquartered in San Francisco, California."}
    )
    assert result.status == "non_eu_domiciled"


def test_ignores_third_party_location_mentions_not_about_the_company_itself() -> None:
    # Real false positive found via live testing: DeepL's own privacy policy
    # mentions that a *subprocessor* (Zoom) is based in the USA - this must
    # not be read as DeepL's own domicile.
    result = classify_eu_domicile(
        {
            "privacy-policy": (
                "Video call support processing takes place on servers in the European Union. "
                "As Zoom is based in the USA, we require a data processing agreement with them."
            )
        }
    )
    assert result.status == "unclear"


def test_ignores_third_party_location_mention_for_dispute_resolution_provider() -> None:
    # Real false positive found via live testing: Fathom/You.com's terms
    # mention JAMS (a dispute-resolution provider) being US-based.
    result = classify_eu_domicile(
        {"terms": "We refer disputes under the U.S. DPF to JAMS, an alternative dispute resolution provider based in the United States."}
    )
    assert result.status == "unclear"


def test_third_person_legal_imprint_recognized_via_provider_name() -> None:
    # Legal imprints commonly state facts in third person using the
    # company's own name ("DeepL SE, registered in Cologne, is...") with no
    # first-person pronoun anywhere - provider_name is the self-reference
    # anchor for this case.
    result = classify_eu_domicile(
        {"imprint": "DeepL SE, a company registered in Cologne, is the data controller."},
        provider_name="DeepL",
    )
    assert result.status == "eu_domiciled"


def test_third_person_phrasing_without_provider_name_is_unclear() -> None:
    # Without a provider_name hint, third-person phrasing has no
    # self-reference signal to anchor on - correctly stays unclear rather
    # than guessing.
    result = classify_eu_domicile({"imprint": "DeepL SE, a company registered in Cologne, is the data controller."})
    assert result.status == "unclear"


def test_unclear_when_no_domicile_statement_present() -> None:
    result = classify_eu_domicile({"docs": "This page describes our API rate limits and pricing tiers."})
    assert result.status == "unclear"


def test_unclear_for_empty_input() -> None:
    result = classify_eu_domicile({})
    assert result.status == "unclear"


def test_negated_domicile_statement_is_not_misread() -> None:
    result = classify_eu_domicile(
        {"faq": "We are not headquartered in the United States - our registered office is in Dublin, Ireland."}
    )
    # "not headquartered in the United States" should be suppressed by the
    # negation check; the genuine Ireland statement should still be found.
    assert result.status == "eu_domiciled"


def test_classifies_eu_domiciled_from_own_vat_number() -> None:
    # A company's own VAT ID on its own imprint page - the single most
    # common structural signal an imprint page carries.
    result = classify_eu_domicile(
        {"imprint": "Our VAT ID: DE123456789 is registered with the local tax office in Munich."}
    )
    assert result.status == "eu_domiciled"


def test_classifies_eu_domiciled_from_own_company_registry_reference() -> None:
    result = classify_eu_domicile(
        {"imprint": "Example GmbH, Handelsregister HRB 98765, Munich District Court."},
        provider_name="Example",
    )
    assert result.status == "eu_domiciled"


def test_classifies_real_mistral_legal_notice_as_eu_domiciled() -> None:
    # Regression test for the actual root cause of this rework: Mistral's
    # real legal-notice page (mistral.ai/legal/) states the company name,
    # then continues in one long sentence through registry number and
    # registered address - ~120+ chars past the company name, well beyond
    # the 80-char lookback used for location phrases. Captured live
    # 2026-07-28.
    result = classify_eu_domicile(
        {
            "mistral-company-info": (
                "In accordance with the provisions of article 6(I) (1) of law no. 2004-575 of 21 June 2004 "
                "on confidence in the digital economy, the publisher of the website https://mistral.ai is: "
                "Mistral, a simplified joint stock company with capital of EUR 15,000, listed on the Paris "
                "Trade and Companies Register (R.C.S.) under number 952 418 325, with registered offices at "
                "15 RUE DES HALLES, 75001 PARIS, FRANCE."
            )
        },
        provider_name="Mistral AI",
    )
    assert result.status == "eu_domiciled"


def test_conflicting_when_two_sources_make_contradictory_self_referential_claims() -> None:
    # Two of the provider's own enabled sources disagree - e.g. an outdated
    # imprint still naming a since-relocated entity. Must not silently pick
    # whichever pattern list happens to be checked first.
    result = classify_eu_domicile(
        {
            "old-imprint": "We are headquartered in Germany and comply with the GDPR as a data controller.",
            "new-terms": "Acme Inc. is a Delaware corporation. We are headquartered in San Francisco, California.",
        }
    )
    assert result.status == "conflicting"
    assert result.evidence_quote is not None
    assert result.evidence_source_key == "old-imprint"
    assert result.conflicting_quote is not None
    assert result.conflicting_source_key == "new-terms"


def test_not_conflicting_when_only_one_side_has_evidence() -> None:
    result = classify_eu_domicile(
        {"imprint": "We are headquartered in Germany and comply with the GDPR as a data controller."}
    )
    assert result.status == "eu_domiciled"
    assert result.conflicting_quote is None
    assert result.conflicting_source_key is None


def test_ignores_third_party_vat_number_mention() -> None:
    # Mirrors the DeepL/Zoom and Fathom/JAMS false positives already fixed
    # for location statements - a subprocessor's own VAT number, disclosed
    # in a DPA/subprocessor table, must not be read as the vendor's own.
    result = classify_eu_domicile(
        {
            "privacy-policy": (
                "Subprocessor Stripe Payments Europe Ltd, VAT ID: IE123456789, "
                "handles invoicing on our behalf."
            )
        }
    )
    assert result.status == "unclear"
