import httpx
import pytest

from app.tracker.registries import lookup_brreg, lookup_gleif


def _mock_get(handler):
    def fake_get(url, params=None, timeout=None, headers=None):
        request = httpx.Request("GET", url, params=params)
        response = handler(request)
        # A real httpx.get() response always has .request attached;
        # raise_for_status() requires it even for a 2xx response.
        response.request = request
        return response

    return fake_get


def test_lookup_gleif_returns_the_first_active_match(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "attributes": {
                            "entity": {
                                "legalName": {"name": "Mistral AI SAS"},
                                "legalAddress": {"country": "FR"},
                                "status": "ACTIVE",
                            }
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "get", _mock_get(handler))
    result = lookup_gleif("Mistral AI")

    assert result is not None
    assert result.country_code == "FR"
    assert result.matched_name == "Mistral AI SAS"
    assert result.source == "gleif"


def test_lookup_gleif_skips_inactive_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "attributes": {
                            "entity": {
                                "legalName": {"name": "Example Corp"},
                                "legalAddress": {"country": "US"},
                                "status": "RETIRED",
                            }
                        }
                    },
                    {
                        "attributes": {
                            "entity": {
                                "legalName": {"name": "Example Corp"},
                                "legalAddress": {"country": "DE"},
                                "status": "ACTIVE",
                            }
                        }
                    },
                ]
            },
        )

    monkeypatch.setattr(httpx, "get", _mock_get(handler))
    result = lookup_gleif("Example Corp")

    assert result is not None
    assert result.country_code == "DE"


def test_lookup_gleif_rejects_a_name_match_that_isnt_actually_the_same_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Real false positive found via a live run against all 41 providers
    # (2026-07-29): a short/generic query name can hit a completely
    # unrelated company that merely contains it as a substring - a
    # registry match is only trusted when the name is exact once legal-form
    # suffixes are stripped from both sides, not just "contains".
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "attributes": {
                            "entity": {
                                "legalName": {"name": "Runway Motors Private Limited"},
                                "legalAddress": {"country": "IN"},
                                "status": "ACTIVE",
                            }
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "get", _mock_get(handler))
    result = lookup_gleif("Runway")

    assert result is None


def test_lookup_gleif_returns_none_on_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    monkeypatch.setattr(httpx, "get", _mock_get(handler))
    result = lookup_gleif("Totally Unknown Company")

    assert result is None


def test_lookup_gleif_returns_none_on_network_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url, params=None, timeout=None, headers=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = lookup_gleif("Anything")

    assert result is None


def test_lookup_brreg_returns_a_norwegian_match(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"_embedded": {"enheter": [{"navn": "Example Norge AS", "organisasjonsnummer": "123456789"}]}},
        )

    monkeypatch.setattr(httpx, "get", _mock_get(handler))
    result = lookup_brreg("Example Norge")

    assert result is not None
    assert result.country_code == "NO"
    assert result.matched_name == "Example Norge AS"
    assert result.source == "brreg"


def test_lookup_brreg_rejects_a_name_match_that_isnt_actually_the_same_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mirrors the real "Canva" -> "Canva Bioorganics LLP" and "Grain" ->
    # "Grain Fundacion" false positives found while verifying live.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"_embedded": {"enheter": [{"navn": "Grain Fundacion Norge", "organisasjonsnummer": "999999999"}]}},
        )

    monkeypatch.setattr(httpx, "get", _mock_get(handler))
    result = lookup_brreg("Grain")

    assert result is None


def test_lookup_brreg_returns_none_on_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"_embedded": {"enheter": []}})

    monkeypatch.setattr(httpx, "get", _mock_get(handler))
    result = lookup_brreg("Nonexistent Company")

    assert result is None
