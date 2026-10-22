from dataclasses import dataclass
from pathlib import Path
import os
import math

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./.local/workbench.db"
    mode: str = "demo"
    public_url: str = "http://localhost:8000"
    auto_migrate: bool = True
    embedded_worker: bool = True
    api_token: str = ""
    patient_ids: tuple[str, ...] = ()
    fhir_base_url: str = "http://localhost:8080/fhir"
    fhir_token: str = ""
    model: str = "gpt-4o-mini"
    hosted_llm: bool = False
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    session_key: str = ""
    smart_client_id: str = ""
    smart_fhir_url: str = ""
    smart_authorization_url: str = ""
    smart_token_url: str = ""
    secure_cookies: bool = False

    @classmethod
    def from_env(cls):
        mode = os.getenv("WORKBENCH_MODE", "demo")
        if mode not in {"demo", "fhir"}:
            raise ValueError("WORKBENCH_MODE must be demo or fhir")
        settings = cls(
            database_url=os.getenv(
                "WORKBENCH_DATABASE_URL", f"sqlite:///{(ROOT / '.local' / 'workbench.db').as_posix()}"
            ),
            mode=mode,
            public_url=os.getenv("WORKBENCH_PUBLIC_URL", "http://localhost:8000").rstrip("/"),
            auto_migrate=os.getenv("WORKBENCH_AUTO_MIGRATE", "true" if mode == "demo" else "false").lower()
            == "true",
            embedded_worker=os.getenv("WORKBENCH_EMBEDDED_WORKER", "true").lower() == "true",
            api_token=os.getenv("WORKBENCH_API_TOKEN", ""),
            patient_ids=tuple(
                filter(None, (x.strip() for x in os.getenv("WORKBENCH_PATIENT_IDS", "").split(",")))
            ),
            fhir_base_url=os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir"),
            fhir_token=os.getenv("WORKBENCH_FHIR_TOKEN", ""),
            model=os.getenv("WORKBENCH_MODEL", "gpt-4o-mini"),
            hosted_llm=os.getenv("WORKBENCH_HOSTED_LLM", "false").lower() == "true",
            input_price_per_million=float(os.environ["WORKBENCH_INPUT_USD_PER_MILLION"])
            if os.getenv("WORKBENCH_INPUT_USD_PER_MILLION")
            else None,
            output_price_per_million=float(os.environ["WORKBENCH_OUTPUT_USD_PER_MILLION"])
            if os.getenv("WORKBENCH_OUTPUT_USD_PER_MILLION")
            else None,
            session_key=os.getenv("WORKBENCH_SESSION_KEY", ""),
            smart_client_id=os.getenv("SMART_CLIENT_ID", ""),
            smart_fhir_url=os.getenv("SMART_FHIR_URL", "").rstrip("/"),
            smart_authorization_url=os.getenv("SMART_AUTHORIZATION_URL", ""),
            smart_token_url=os.getenv("SMART_TOKEN_URL", ""),
            secure_cookies=os.getenv(
                "WORKBENCH_SECURE_COOKIES", "false" if mode == "demo" else "true"
            ).lower()
            == "true",
        )
        if mode == "fhir" and not settings.api_token and not settings.smart_client_id:
            raise ValueError("FHIR mode requires a scoped API token or SMART configuration")
        if settings.api_token and len(settings.api_token) < 32:
            raise ValueError("WORKBENCH_API_TOKEN must contain at least 32 characters")
        if mode == "fhir" and settings.api_token and not settings.patient_ids:
            raise ValueError("WORKBENCH_PATIENT_IDS is required for service-token access")
        if settings.smart_client_id and not all(
            (
                settings.session_key,
                settings.smart_fhir_url,
                settings.smart_authorization_url,
                settings.smart_token_url,
            )
        ):
            raise ValueError("SMART launch requires encryption key and all pinned endpoints")
        for price in (settings.input_price_per_million, settings.output_price_per_million):
            if price is not None and (not math.isfinite(price) or price < 0):
                raise ValueError("Configured token prices must be finite and non-negative")
        return settings
