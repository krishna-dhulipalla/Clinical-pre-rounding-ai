from unittest.mock import Mock

import pytest
import requests

from fhir.client import FHIRClient, FHIRRequestError


def response(payload, status=200):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(response=result)
    return result


def test_search_follows_pagination_without_reusing_search_params(monkeypatch):
    first = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Observation", "id": "a"}}],
        "link": [{"relation": "next", "url": "http://localhost:8080/fhir?_getpages=token"}],
    }
    second = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Observation", "id": "b"}}],
    }
    get = Mock(side_effect=[response(first), response(second)])
    monkeypatch.setattr(requests, "get", get)
    facts = FHIRClient().search_observations("p", "laboratory")
    assert [fact["id"] for fact in facts] == ["a", "b"]
    assert get.call_args_list[0].kwargs["params"]["subject"] == "Patient/p"
    assert get.call_args_list[1].kwargs["params"] is None
    assert all(call.kwargs["timeout"] == (5, 30) for call in get.call_args_list)


@pytest.mark.parametrize("failure", [requests.Timeout(), requests.ConnectionError()])
def test_network_failure_does_not_become_an_empty_search(monkeypatch, failure):
    monkeypatch.setattr(requests, "get", Mock(side_effect=failure))
    with pytest.raises(FHIRRequestError, match="retrieval failed"):
        FHIRClient().search_encounters("p")


def test_patient_not_found_is_distinct_from_server_failure(monkeypatch):
    monkeypatch.setattr(requests, "get", Mock(return_value=response({}, 404)))
    assert FHIRClient().get_patient("missing") is None
    monkeypatch.setattr(requests, "get", Mock(return_value=response({}, 503)))
    with pytest.raises(FHIRRequestError):
        FHIRClient().get_patient("p")


@pytest.mark.parametrize("next_url", ["http://other-server/fhir?page=2", "?page=2"])
def test_unsafe_or_repeating_pagination_fails_explicitly(monkeypatch, next_url):
    bundle = {"resourceType": "Bundle", "link": [{"relation": "next", "url": next_url}]}
    get = Mock(return_value=response(bundle))
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(FHIRRequestError):
        FHIRClient().search_observations("p")
    assert get.call_count <= 2


@pytest.mark.parametrize("payload", [[], {"resourceType": "OperationOutcome"}])
def test_invalid_search_result_is_not_summarized(monkeypatch, payload):
    monkeypatch.setattr(requests, "get", Mock(return_value=response(payload)))
    with pytest.raises(FHIRRequestError):
        FHIRClient().search_observations("p")


def test_bad_json_is_reported_as_retrieval_failure(monkeypatch):
    result = response(None)
    result.json.side_effect = ValueError("invalid JSON")
    monkeypatch.setattr(requests, "get", Mock(return_value=result))
    with pytest.raises(FHIRRequestError, match="invalid JSON"):
        FHIRClient().search_observations("p")
