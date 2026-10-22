import base64
import hashlib
import re
import secrets
from time import time
from urllib.parse import urlencode, urlsplit

import requests
from sqlalchemy import delete

from .persistence import OAuthFlow
from .security import token_hash


class SmartLaunch:
    """Pinned sandbox issuer/endpoints, browser-bound state, PKCE, server-only tokens."""

    def __init__(self, database, settings, auth):
        self.database, self.settings, self.auth = database, settings, auth

    def enabled(self):
        return bool(self.settings.mode == "fhir" and self.settings.smart_client_id and self.auth.cipher)

    def begin(self, issuer, launch=None):
        cfg = self.settings
        if not self.enabled() or not cfg.smart_fhir_url or issuer.rstrip("/") != cfg.smart_fhir_url:
            raise PermissionError("Unconfigured SMART issuer")
        for url in (cfg.smart_fhir_url, cfg.smart_authorization_url, cfg.smart_token_url):
            parts = urlsplit(url)
            if parts.scheme != "https" and not (
                parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"}
            ):
                raise ValueError("Pin HTTPS SMART endpoints or use a local sandbox")
            if parts.username or parts.password or parts.fragment or parts.query:
                raise ValueError("SMART endpoint URLs cannot contain credentials, query or fragment")
        response = requests.get(
            cfg.smart_fhir_url + "/.well-known/smart-configuration", timeout=(5, 15), allow_redirects=False
        )
        if response.status_code != 200:
            raise ValueError("SMART discovery failed")
        metadata = response.json()
        if (
            metadata.get("authorization_endpoint") != cfg.smart_authorization_url
            or metadata.get("token_endpoint") != cfg.smart_token_url
        ):
            raise ValueError("SMART discovery does not match pinned endpoints")
        if "S256" not in metadata.get("code_challenge_methods_supported", []):
            raise ValueError("SMART server must support PKCE S256")
        state, browser, verifier = (
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(64),
        )
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        with self.database.sessions.begin() as db:
            db.execute(delete(OAuthFlow).where(OAuthFlow.expires_at < time()))
            db.add(
                OAuthFlow(
                    state_hash=token_hash(state),
                    browser_hash=token_hash(browser),
                    verifier=verifier,
                    token_url=cfg.smart_token_url,
                    fhir_url=cfg.smart_fhir_url,
                    expires_at=time() + 300,
                )
            )
        scopes = "launch launch/patient launch/encounter" if launch else "launch/patient launch/encounter"
        scopes += " patient/Patient.rs patient/Encounter.rs patient/Observation.rs patient/MedicationRequest.rs patient/MedicationAdministration.rs"
        params = {
            "response_type": "code",
            "client_id": cfg.smart_client_id,
            "redirect_uri": cfg.public_url + "/api/smart/callback",
            "scope": scopes,
            "state": state,
            "aud": cfg.smart_fhir_url,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if launch:
            params["launch"] = launch
        return cfg.smart_authorization_url + "?" + urlencode(params), browser

    def finish(self, state, browser, code):
        if not self.enabled() or not browser or not state or not code:
            raise PermissionError("Invalid SMART callback")
        with self.database.sessions.begin() as db:
            flow = db.get(OAuthFlow, token_hash(state))
            if not flow or flow.expires_at < time() or flow.browser_hash != token_hash(browser):
                raise PermissionError("Invalid or expired browser-bound SMART state")
            # Atomic consumption prevents a second callback from reusing the authorization code.
            consumed = db.execute(delete(OAuthFlow).where(OAuthFlow.state_hash == flow.state_hash)).rowcount
            if consumed != 1:
                raise PermissionError("SMART callback already consumed")
        result = requests.post(
            flow.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.settings.smart_client_id,
                "redirect_uri": self.settings.public_url + "/api/smart/callback",
                "code_verifier": flow.verifier,
            },
            headers={"Accept": "application/json"},
            timeout=(5, 15),
            allow_redirects=False,
        )
        if result.status_code != 200:
            raise PermissionError("SMART token exchange failed")
        token = result.json()
        patient, encounter = token.get("patient"), token.get("encounter")
        if not isinstance(patient, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,64}", patient):
            raise PermissionError("SMART did not return a valid patient context")
        if encounter and (
            not isinstance(encounter, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,64}", encounter)
        ):
            raise PermissionError("SMART returned invalid encounter context")
        scopes = token.get("scope", "").split()
        if not any(
            scope.startswith("patient/") and scope.rsplit(".", 1)[-1] in {"rs", "read", "cruds"}
            for scope in scopes
        ):
            raise PermissionError("SMART patient read scope was not granted")
        access_token = token.get("access_token")
        ttl = min(int(token.get("expires_in", 300)), 3600)
        if (
            not isinstance(access_token, str)
            or not access_token
            or ttl <= 0
            or token.get("token_type", "").lower() != "bearer"
        ):
            raise PermissionError("Invalid SMART access token")
        # No unverified ID-token identity is trusted. The actor is this authorized launch session.
        return self.auth.issue(
            "smart-" + secrets.token_hex(12),
            "SMART authorized session",
            [patient],
            ttl,
            encounter_id=encounter,
            access_token=access_token,
            fhir_url=flow.fhir_url,
        )
