from contextlib import asynccontextmanager
from time import perf_counter, time
from uuid import uuid4
import json
import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from fhir.client import FHIRRequestError
from .config import ROOT, Settings
from .demo import DEMO_CLOCK, PATIENTS
from .domain import ReviewRequest, RunRequest
from .persistence import AccessEvent, Database, SnapshotRow
from .pipeline import EvidenceIntegrityError
from .security import Auth, Principal
from .service import Conflict, Workbench
from .smart import SmartLaunch
from .sources import matches_reference
from .worker import Worker

logger = logging.getLogger("workbench.api")


def create_app(settings=None, database=None):
    from .logging import configure_logging

    configure_logging()
    settings = settings or Settings.from_env()
    database = database or Database(settings.database_url)
    auth = Auth(database, settings)
    service = Workbench(database, settings, auth)
    worker = Worker(database, settings, auth)
    smart = SmartLaunch(database, settings, auth)

    @asynccontextmanager
    async def lifespan(app):
        if settings.auto_migrate:
            database.migrate()
        if not database.ready():
            raise RuntimeError("Database migration is required")
        if settings.embedded_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(
        title="Clinical Change Intelligence Workbench",
        version="2.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.database, app.state.worker, app.state.service, app.state.auth, app.state.smart = (
        database,
        worker,
        service,
        auth,
        smart,
    )

    @app.middleware("http")
    async def request_context(request, call_next):
        started = perf_counter()
        request.state.trace_id = str(uuid4())
        blocked = False
        if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if request.headers.get("x-workbench-request") != "1" or (
                origin and origin != settings.public_url
            ):
                blocked = True
        try:
            response = (
                JSONResponse({"detail": "Invalid same-origin request"}, status_code=403)
                if blocked
                else await call_next(request)
            )
        except Exception:
            logger.error(json.dumps({"event": "request_failed", "trace_id": request.state.trace_id}))
            response = JSONResponse(
                {"detail": "Request failed", "trace_id": request.state.trace_id}, status_code=500
            )
        response.headers["X-Trace-ID"] = request.state.trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        # The route template avoids IDs, query strings, tokens and patient text in logs.
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "route": getattr(route, "path", "static"),
                    "status": response.status_code,
                    "trace_id": request.state.trace_id,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(PermissionError)
    async def denied(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Record not found"}, status_code=404)

    @app.exception_handler(EvidenceIntegrityError)
    async def integrity(request, exc):
        return JSONResponse(
            {"detail": "Evidence integrity validation failed", "trace_id": request.state.trace_id},
            status_code=409,
        )

    @app.exception_handler(FHIRRequestError)
    async def upstream(request, exc):
        return JSONResponse(
            {"detail": "FHIR retrieval unavailable; no empty result was inferred"}, status_code=502
        )

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def principal(request: Request):
        header = request.headers.get("authorization", "")
        bearer = header.removeprefix("Bearer ") if header.startswith("Bearer ") else None
        current = auth.resolve(request.cookies.get("wb_session"), bearer)
        if not current:
            raise HTTPException(401, "Sign in or launch from the configured SMART sandbox")
        return current

    def cookie(response, token):
        response.set_cookie(
            "wb_session",
            token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            max_age=8 * 3600,
            path="/",
        )

    @app.get("/health/live")
    def live():
        return {"status": "alive", "version": "2.0.0"}

    @app.get("/health/ready")
    def ready(response: Response):
        try:
            available = database.ready()
            if settings.embedded_worker:
                available = (
                    available
                    and worker.thread is not None
                    and worker.thread.is_alive()
                    and time() - worker.last_poll < 30
                )
        except Exception:
            available = False
        response.status_code = 200 if available else 503
        return {"ready": available, "database": "connected" if available else "check required"}

    @app.get("/api/config")
    def config(request: Request):
        return {
            "mode": settings.mode,
            "demo_clock": DEMO_CLOCK.isoformat() if settings.mode == "demo" else None,
            "smart_enabled": smart.enabled(),
            "hosted_ranking": settings.hosted_llm,
            "version": "2.0.0",
            "session_active": auth.resolve(request.cookies.get("wb_session")) is not None,
        }

    @app.post("/api/session/demo")
    def demo_login(request: Request, response: Response):
        if settings.mode != "demo":
            raise PermissionError("Demo sessions are disabled")
        auth.revoke(request.cookies.get("wb_session"))
        token, user = auth.demo_session()
        cookie(response, token)
        service.audit(user, "session.started", request.state.trace_id)
        return {"actor_id": user.actor_id, "display_name": user.display_name, "patient_ids": user.patient_ids}

    @app.get("/api/session")
    def session(user: Principal = Depends(principal)):
        return {
            "actor_id": user.actor_id,
            "display_name": user.display_name,
            "patient_ids": user.patient_ids,
            "encounter_id": user.encounter_id,
        }

    @app.post("/api/session/logout")
    def logout(request: Request, response: Response, user: Principal = Depends(principal)):
        service.audit(user, "session.ended", request.state.trace_id)
        auth.revoke(request.cookies.get("wb_session"))
        response.delete_cookie("wb_session", path="/")
        return {"signed_out": True}

    @app.get("/api/patients")
    def patients(request: Request, user: Principal = Depends(principal)):
        source = auth.source(user)
        rows = []
        for patient_id in user.patient_ids:
            if settings.mode == "demo":
                row = dict(next(p for p in PATIENTS if p["id"] == patient_id))
            else:
                patient = source.patient(patient_id)
                if patient.get("id") != patient_id:
                    raise EvidenceIntegrityError("Patient read mismatch")
                name = next(iter(patient.get("name", [])), {})
                row = {
                    "id": patient_id,
                    "name": name.get("text")
                    or " ".join(name.get("given", []) + [name.get("family", "")]).strip()
                    or "Patient",
                    "room": "FHIR context",
                    "focus": "Encounter review",
                }
            rows.append(row)
        service.audit(user, "worklist.viewed", request.state.trace_id)
        return rows

    @app.get("/api/patients/{patient_id}/encounters")
    def encounters(patient_id: str, request: Request, user: Principal = Depends(principal)):
        service.authorize(user, patient_id, request.state.trace_id)
        source = auth.source(user)
        rows = source.encounters(patient_id)
        result = []
        for row in rows:
            if not matches_reference(
                row.get("subject", {}).get("reference", ""), "Patient", patient_id, source.base_url
            ):
                raise EvidenceIntegrityError("Encounter read mismatch")
            if not user.encounter_id or row["id"] == user.encounter_id:
                result.append({"id": row["id"], "status": row.get("status"), "period": row.get("period", {})})
        service.audit(user, "encounters.viewed", request.state.trace_id, patient_id)
        return result

    @app.post("/api/runs", status_code=202)
    def create_run(
        payload: RunRequest,
        request: Request,
        idempotency_key: str = Header(min_length=8, max_length=128),
        user: Principal = Depends(principal),
    ):
        if payload.as_of.timestamp() > time() + 300 and settings.mode != "demo":
            raise ValueError("Review time cannot be in the future")
        return service.enqueue(user, payload, idempotency_key, request.state.trace_id)

    @app.get("/api/runs")
    def runs(request: Request, user: Principal = Depends(principal)):
        service.audit(user, "runs.listed", request.state.trace_id)
        return service.list_runs(user)

    @app.get("/api/runs/{run_id}")
    def run(run_id: str, request: Request, user: Principal = Depends(principal)):
        return service.detail(user, run_id, request.state.trace_id)

    @app.post("/api/runs/{run_id}/cancel")
    def cancel(run_id: str, request: Request, user: Principal = Depends(principal)):
        return service.cancel(user, run_id, request.state.trace_id)

    @app.get("/api/runs/{run_id}/evidence/{evidence_id}")
    def evidence(run_id: str, evidence_id: str, request: Request, user: Principal = Depends(principal)):
        return service.evidence(user, run_id, evidence_id, request.state.trace_id)

    @app.post("/api/runs/{run_id}/reviews")
    def review(run_id: str, payload: ReviewRequest, request: Request, user: Principal = Depends(principal)):
        return service.review(user, run_id, payload, request.state.trace_id)

    @app.get("/api/operations")
    def operations(request: Request, user: Principal = Depends(principal)):
        service.audit(user, "operations.viewed", request.state.trace_id)
        runs = service.list_runs(user)
        ids = [row["id"] for row in runs]
        durations, tokens, audits, costs = [], 0, [], []
        with database.sessions() as db:
            for record in db.scalars(select(SnapshotRow).where(SnapshotRow.run_id.in_(ids))):
                telemetry = record.payload.get("telemetry", {})
                durations.append(telemetry.get("total_ms", 0))
                tokens += telemetry.get("input_tokens", 0) + telemetry.get("output_tokens", 0)
                costs.append(telemetry.get("estimated_cost_usd"))
            events = db.scalars(
                select(AccessEvent)
                .where(AccessEvent.actor_id == user.actor_id)
                .order_by(AccessEvent.created_at.desc())
                .limit(50)
            )
            audits = [
                {
                    "action": event.action,
                    "outcome": event.outcome,
                    "created_at": datetime_iso(event.created_at),
                    "trace_id": event.trace_id,
                }
                for event in events
            ]
        durations.sort()
        return {
            "scope": "Latest 100 runs for this principal",
            "total_runs": len(runs),
            "completed": sum(r["status"] == "completed" for r in runs),
            "abstained": sum(r["status"] == "abstained" for r in runs),
            "failed": sum(r["status"] == "failed" for r in runs),
            "accepted": sum(r["review_status"] == "accepted" for r in runs),
            "p95_ms": durations[max(0, int(len(durations) * 0.95 + 0.999) - 1)] if durations else None,
            "total_tokens": tokens,
            "cost_usd": round(sum(costs), 6) if costs and all(cost is not None for cost in costs) else None,
            "cost_note": "Estimated from configured token rates; excludes hosting and other services"
            if costs and all(cost is not None for cost in costs)
            else "Token rates not configured or a model call failed; estimated cost is unavailable",
            "events": audits,
        }

    @app.get("/api/evaluation")
    def evaluation(request: Request, user: Principal = Depends(principal)):
        from .evaluation import evaluate

        service.audit(user, "evaluation.viewed", request.state.trace_id)
        return evaluate()

    @app.get("/api/smart/launch")
    def smart_launch(iss: str, launch: str | None = None):
        url, browser = smart.begin(iss, launch)
        response = RedirectResponse(url, status_code=302)
        response.set_cookie(
            "wb_launch",
            browser,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            max_age=300,
            path="/api/smart",
        )
        return response

    @app.get("/api/smart/callback")
    def smart_callback(request: Request, state: str = "", code: str = ""):
        try:
            token, user = smart.finish(state, request.cookies.get("wb_launch"), code)
        except Exception:
            raise HTTPException(403, "SMART launch failed. Start a new launch from the configured sandbox")
        response = RedirectResponse(settings.public_url + "/", status_code=302)
        cookie(response, token)
        response.delete_cookie("wb_launch", path="/api/smart")
        service.audit(user, "smart.session.started", request.state.trace_id)
        return response

    dist = ROOT / "web" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def frontend():
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return JSONResponse(
            {
                "detail": "Build the frontend with npm ci and npm run build in web/",
                "api_schema": "/openapi.json",
            },
            status_code=503,
        )

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(ROOT / "web" / "public" / "favicon.svg", media_type="image/svg+xml")

    return app


def datetime_iso(value):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value, timezone.utc).isoformat()
