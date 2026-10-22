from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
import pytest

from workbench.config import Settings
from workbench.persistence import Database, SessionRow
from workbench.security import Auth
from workbench.smart import SmartLaunch


@pytest.fixture
def smart(tmp_path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'smart.db').as_posix()}",
        mode="fhir",
        public_url="http://testserver",
        smart_client_id="sandbox-app",
        smart_fhir_url="https://fhir.example/r4",
        smart_authorization_url="https://auth.example/authorize",
        smart_token_url="https://auth.example/token",
        session_key=Fernet.generate_key().decode(),
    )
    database = Database(settings.database_url)
    database.migrate()
    auth = Auth(database, settings)
    flow = SmartLaunch(database, settings, auth)
    metadata = Mock(status_code=200)
    metadata.json.return_value = {
        "authorization_endpoint": settings.smart_authorization_url,
        "token_endpoint": settings.smart_token_url,
        "code_challenge_methods_supported": ["S256"],
    }
    monkeypatch.setattr("workbench.smart.requests.get", Mock(return_value=metadata))
    token_response = Mock(status_code=200)
    token_response.json.return_value = {
        "access_token": "upstream-secret-token",
        "token_type": "Bearer",
        "expires_in": 300,
        "patient": "patient-1",
        "encounter": "enc-1",
        "scope": "patient/Observation.rs",
    }
    monkeypatch.setattr("workbench.smart.requests.post", Mock(return_value=token_response))
    yield flow, auth, metadata, token_response
    database.engine.dispose()


def test_pkce_browser_bound_state_and_encrypted_tokens(smart):
    flow, auth, _, _ = smart
    url, browser = flow.begin("https://fhir.example/r4", "ehr-launch-token")
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["aud"] == ["https://fhir.example/r4"]
    assert query["launch"] == ["ehr-launch-token"]
    token, principal = flow.finish(query["state"][0], browser, "authorization-code")
    assert principal.patient_ids == ("patient-1",)
    assert principal.encounter_id == "enc-1"
    assert principal.actor_id.startswith("smart-")
    resolved = auth.resolve(cookie=token)
    assert resolved == principal
    with auth.database.sessions() as db:
        stored = db.get(SessionRow, principal.session_hash)
        assert "upstream-secret-token" not in stored.token_ciphertext
        assert auth.cipher.decrypt(stored.token_ciphertext.encode()).decode() == "upstream-secret-token"
    with pytest.raises(PermissionError):
        flow.finish(query["state"][0], browser, "authorization-code")


def test_foreign_issuer_and_browser_cannot_complete_launch(smart):
    flow, _, _, _ = smart
    with pytest.raises(PermissionError):
        flow.begin("https://attacker.example/r4")
    url, _ = flow.begin("https://fhir.example/r4")
    with pytest.raises(PermissionError):
        flow.finish(parse_qs(urlsplit(url).query)["state"][0], "other-browser", "code")


def test_discovery_cannot_redirect_tokens_to_an_unpinned_endpoint(smart):
    flow, _, metadata, _ = smart
    metadata.json.return_value["token_endpoint"] = "https://attacker.example/token"
    with pytest.raises(ValueError, match="pinned"):
        flow.begin("https://fhir.example/r4")


@pytest.mark.parametrize(
    "field,value", [("patient", None), ("scope", "user/*.rs"), ("token_type", "MAC"), ("expires_in", -1)]
)
def test_invalid_token_context_is_rejected(smart, field, value):
    flow, _, _, token_response = smart
    token_response.json.return_value[field] = value
    url, browser = flow.begin("https://fhir.example/r4")
    with pytest.raises(PermissionError):
        flow.finish(parse_qs(urlsplit(url).query)["state"][0], browser, "code")
