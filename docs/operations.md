# Running and operating v2

## Local topology

Run `uv sync --frozen --extra dev`, `npm --prefix web ci`, `npm --prefix web run build`, then `uv run python scripts/run_workbench.py serve` from the repository root. The default listener is localhost only. `WORKBENCH_PUBLIC_URL` must match the browser origin, including port, for mutation requests.

V2 uses a separate `WORKBENCH_DATABASE_URL`, defaulting to `.local/workbench.db`. It never migrates the legacy v1 `audit_logs` table. Synthetic demo mode auto-migrates the v2 tables. In FHIR mode, automatic migrations default off.

To develop the frontend with Vite, set `WORKBENCH_PUBLIC_URL=http://localhost:5173`, run the API, then run `npm --prefix web run dev -- --host localhost`. Vite proxies `/api` to port 8000. Use the built same-origin server for final verification.

## Separate worker and migrations

Set `WORKBENCH_EMBEDDED_WORKER=false` in the API environment and use the same database/configuration in the worker:

```powershell
uv run python scripts/run_workbench.py migrate
uv run python scripts/run_workbench.py worker
uv run python scripts/run_workbench.py serve
```

Jobs persist in `wb_runs`. Workers claim with conditional database updates, renew a five-minute lease while processing, and reclaim abandoned jobs after expiry. Recovery stops after three attempts. Requests carry an idempotency key; reuse with a different request produces a conflict. Cancellation prevents a worker from publishing a result but does not interrupt a request already sent to an upstream server/provider.

Snapshots, completion state, and completion access events commit together. Review revisions use optimistic concurrency: the client must supply the current revision. A conflict requires reload rather than silently overwriting another review.

## Health and telemetry

- `/health/live` reports process liveness.
- `/health/ready` checks the schema/database and, for the embedded topology, worker polling health.
- A separate worker is supervised independently; API readiness does not certify that an external worker is processing jobs. Monitor queued/running job age and worker process health.
- Authenticated `/api/operations` reports the current principal's latest 100 runs, completion/abstention/failure counts, p95 snapshot processing time, token use, optional estimated model cost, and latest 50 access/review events.
- HTTP responses carry a trace ID. JSON logs use route templates and event/status/timing fields, not patient names, request bodies, raw FHIR data, upstream exception strings, or OAuth callback query parameters.

Use the provided runner or disable Uvicorn access logs in an equivalent launcher. Standard access logs can contain OAuth callback query strings. Named clinician identity federation and a production observability exporter are not part of the sandbox implementation.

## Retention and storage

The evidence database stores original FHIR records, patient IDs, review notes, and review history. SQLite is a local demonstration store; choose managed storage encryption, access roles, backup handling and retention for a deployed environment. Upstream SMART access tokens use the configured Fernet key; losing that key requires new launches.

Preview candidate deletion counts:

```powershell
uv run python scripts/run_workbench.py purge --retention-days 90 --audit-days 365
```

Add `--apply` to delete expired terminal runs, their snapshots/revisions, expired sessions/flows and sufficiently old access events. Running/queued jobs are retained. Audit retention must be at least as long as run retention. The command is not automatically scheduled; retention durations and backups must follow the operator's policy.

Snapshots, revisions, and access events are append-only through application ORM updates. Database administrators still have direct write/delete authority. Fingerprints detect application-level mismatches; they are not signed, external, tamper-proof audit storage.

## Release and rollback

1. Run locked-environment tests, lint, synthetic evaluation and frontend build.
2. Run the PostgreSQL integration CI job and build/test the container with the intended configuration.
3. Back up the database and retain the previous image plus dependency lock files.
4. Apply migrations once through a deployment job; run application instances with automatic migrations disabled.
5. Verify readiness, synthetic failure scenarios, job recovery and review conflicts before routing users.
6. Roll back application images only when schema compatibility is established. Migration `0001_workbench` downgrade removes v2 tables; restore a verified backup instead when preserving evidence/reviews is required.

The provided Compose file is a localhost synthetic deployment example, with local credentials. External TLS, secret management, institutional authorization, rate controls, monitoring, vulnerability scanning, disaster recovery and clinical validation remain deployment responsibilities.

## Validation limits

The local test environment can exercise SQLite, mocked FHIR/model/SMART services, migrations, and browser workflows. Container/PostgreSQL integration requires Docker. A registered SMART sandbox and provider credentials are required for an actual OAuth launch. A configured hosted model is required to measure ranking quality and provider usage. Synthetic fixture success is not evidence of clinical efficacy or regulatory compliance.
