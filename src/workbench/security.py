from dataclasses import dataclass
import hashlib
import hmac
import secrets
from time import time

from cryptography.fernet import Fernet

from .demo import PATIENTS
from .persistence import SessionRow
from .sources import DemoSource, FHIRSource


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    actor_id: str
    display_name: str
    patient_ids: tuple[str, ...]
    session_hash: str | None = None
    encounter_id: str | None = None


class Auth:
    def __init__(self, database, settings):
        self.database, self.settings = database, settings
        self.cipher = Fernet(settings.session_key.encode()) if settings.session_key else None

    def demo_session(self):
        if self.settings.mode != "demo":
            raise PermissionError("Demo sessions are disabled")
        return self.issue(
            "demo-clinician", "Dr. Maya Patel · synthetic role", [p["id"] for p in PATIENTS], 8 * 3600
        )

    def issue(self, actor, name, patient_ids, ttl, encounter_id=None, access_token=None, fhir_url=None):
        if access_token and not self.cipher:
            raise ValueError("Configure WORKBENCH_SESSION_KEY for SMART token encryption")
        token = secrets.token_urlsafe(32)
        row = SessionRow(
            token_hash=token_hash(token),
            actor_id=actor,
            display_name=name,
            patient_ids=patient_ids,
            encounter_id=encounter_id,
            expires_at=time() + ttl,
            token_ciphertext=self.cipher.encrypt(access_token.encode()).decode() if access_token else None,
            fhir_url=fhir_url,
        )
        with self.database.sessions.begin() as db:
            db.add(row)
        return token, Principal(actor, name, tuple(patient_ids), row.token_hash, encounter_id)

    def resolve(self, cookie=None, bearer=None):
        if bearer and self.settings.api_token and hmac.compare_digest(bearer, self.settings.api_token):
            return Principal("service-clinician", "Configured service principal", self.settings.patient_ids)
        if not cookie:
            return None
        with self.database.sessions() as db:
            row = db.get(SessionRow, token_hash(cookie))
            if row and row.expires_at > time():
                if (self.settings.mode == "fhir") != bool(row.token_ciphertext):
                    return None
                return Principal(
                    row.actor_id, row.display_name, tuple(row.patient_ids), row.token_hash, row.encounter_id
                )
        return None

    def source(self, principal):
        if self.settings.mode == "demo":
            return DemoSource()
        if principal.session_hash:
            with self.database.sessions() as db:
                row = db.get(SessionRow, principal.session_hash)
                if not row or row.expires_at <= time():
                    raise PermissionError("Session expired; launch again")
                if row.token_ciphertext:
                    return FHIRSource(
                        row.fhir_url, self.cipher.decrypt(row.token_ciphertext.encode()).decode()
                    )
                raise PermissionError("This session is not authorized for the FHIR deployment")
        return FHIRSource(self.settings.fhir_base_url, self.settings.fhir_token)

    def revoke(self, cookie):
        if cookie:
            with self.database.sessions.begin() as db:
                row = db.get(SessionRow, token_hash(cookie))
                if row:
                    db.delete(row)
