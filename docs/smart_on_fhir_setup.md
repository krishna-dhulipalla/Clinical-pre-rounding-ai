# SMART on FHIR sandbox setup

V2 implements a public-client sandbox launch using PKCE S256. Use the [published SMART 2.2 launch flow](https://hl7.org/fhir/smart-app-launch/STU2.2/app-launch.html) and your provider's registration requirements. This is a sandbox integration, not enterprise identity certification.

## Registration and configuration

Register the application with the chosen sandbox. Configure the exact redirect URI:

```text
http://localhost:8000/api/smart/callback
```

Use HTTPS with secure cookies for a deployed environment. Generate a Fernet token-encryption key without committing it:

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the following in your local environment or secret store:

```ini
WORKBENCH_MODE=fhir
WORKBENCH_PUBLIC_URL=http://localhost:8000
WORKBENCH_DATABASE_URL=postgresql://user:password@localhost:5432/workbench
WORKBENCH_AUTO_MIGRATE=false
WORKBENCH_SESSION_KEY=your-generated-key
SMART_CLIENT_ID=your-registered-public-client
SMART_FHIR_URL=https://your-sandbox.example/fhir
SMART_AUTHORIZATION_URL=https://your-sandbox.example/authorize
SMART_TOKEN_URL=https://your-sandbox.example/token
```

For a local HTTP sandbox only, explicitly set `WORKBENCH_SECURE_COOKIES=false`; otherwise keep secure cookies enabled. Run the migration command before starting FHIR mode.

The FHIR issuer, authorization endpoint and token endpoint are pinned configuration. Discovery must exactly match the configured endpoints and advertise S256 support. Redirected discovery/token requests are rejected. Arbitrary issuer URLs supplied in launch parameters are not accepted.

## Launch

For an EHR launch, register `/api/smart/launch` as the launch URL. The sandbox sends `iss` and `launch`. For a standalone sandbox flow, open `/api/smart/launch?iss=<URL-encoded configured FHIR issuer>`.

The server creates five-minute browser-bound one-time state and a PKCE verifier, requests patient/encounter context and read/search access to Patient, Encounter, Observation, MedicationRequest and MedicationAdministration, and exchanges the authorization code server-side. The returned patient context is required. A returned encounter context further restricts all subsequent run access.

Bearer tokens are encrypted in the session store and never returned to the frontend. Sessions expire no later than the token's reported lifetime or one hour. No refresh token is requested or stored; re-launch after expiry. Logging uses route templates, with access logs disabled to avoid recording authorization codes in callback URLs.

The reviewer identity is an authorized launch-session identifier. Named clinician identity would require validated federation/identity claims and institutional authorization; this implementation does not trust an unverified ID token.

## Service API alternative

For a controlled FHIR API client, configure `WORKBENCH_API_TOKEN` with at least 32 random characters, `WORKBENCH_PATIENT_IDS` with an explicit comma-separated allowlist, and `WORKBENCH_FHIR_TOKEN` for the upstream server when required. Send `Authorization: Bearer <WORKBENCH_API_TOKEN>` and `X-Workbench-Request: 1` on mutation requests. This principal is not a browser login flow.

## Validation boundary

Automated tests mock SMART discovery and token exchange and verify PKCE parameters, browser/state binding, replay rejection, endpoint pinning, token encryption and context validation. A real launch requires your registered sandbox configuration and must be verified there. SMART authorization alone does not establish organizational access policies, auditing compliance, clinical validity or general PHI protection.
