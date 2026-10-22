import { useEffect, useRef, useState } from "react";
import { api, dateTime, inputDate } from "./api";
import type {
  Claim,
  Config,
  Encounter,
  EvalReport,
  Evidence,
  Operations,
  Patient,
  Run,
  User,
} from "./types";

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    pulse: "M3 12h4l3-8 4 16 3-8h4",
    arrow: "M5 12h14m-6-6 6 6-6 6",
    check: "m5 12 4 4L19 6",
    close: "m6 6 12 12M6 18 18 6",
    layers: "m12 3 10 5-10 5L2 8l10-5Zm-9 9 9 5 9-5M3 17l9 5 9-5",
    chart: "M4 20h16M7 16v-5m5 5V5m5 11V8",
    clock: "M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
    file: "M14 2H5v20h14V7l-5-5Zm0 0v6h5M8 12h8m-8 4h6",
    shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6",
    search: "m21 21-5-5m2-6a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.file} />
    </svg>
  );
}

function Status({ state }: { state: string }) {
  return (
    <span className={`status status-${state}`}>
      <span />
      {state.replaceAll("_", " ")}
    </span>
  );
}

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [patientId, setPatientId] = useState("");
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [encounterId, setEncounterId] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [runId, setRunId] = useState("");
  const [page, setPage] = useState("workspace");
  const [since, setSince] = useState("");
  const [asOf, setAsOf] = useState("");
  const [windowStart, setWindowStart] = useState("");
  const [scenario, setScenario] = useState("normal");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceId, setEvidenceId] = useState("");
  const [tab, setTab] = useState("briefing");
  const [query, setQuery] = useState("");
  const [evaluation, setEvaluation] = useState<EvalReport | null>(null);
  const [operations, setOperations] = useState<Operations | null>(null);
  const context = useRef(0);
  const inspection = useRef(0);
  const patient = patients.find((item) => item.id === patientId);
  const snapshot =
    run?.patient_id === patientId && run?.encounter_id === encounterId
      ? run.snapshot
      : null;
  const pending = run?.status === "queued" || run?.status === "running";

  useEffect(() => {
    const expired = () => {
      ++context.current;
      setUser(null);
      setPatients([]);
      setPatientId("");
      setRuns([]);
      setRun(null);
      setRunId("");
      setEvidence(null);
      setEvidenceId("");
      setNote("");
      setSelected([]);
      setNotice("");
      sessionStorage.removeItem("wb_pending");
    };
    window.addEventListener("wb-session-expired", expired);
    return () => window.removeEventListener("wb-session-expired", expired);
  }, []);

  useEffect(() => {
    api<Config>("/config")
      .then(async (data) => {
        setConfig(data);
        if (data.session_active) setUser(await api<User>("/session"));
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    Promise.all([
      api<Patient[]>("/patients", {}, controller.signal),
      api<Run[]>("/runs", {}, controller.signal),
    ])
      .then(([items, history]) => {
        setRuns(history);
        setPatients(items);
        setPatientId(items[0]?.id || "");
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [user]);

  useEffect(() => {
    const revision = ++context.current;
    setRun(null);
    setRunId("");
    setEvidence(null);
    setEvidenceId("");
    setSelected([]);
    setNote("");
    setNotice("");
    setError("");
    setEncounters([]);
    setEncounterId("");
    setScenario("normal");
    setTab("briefing");
    if (!patientId || !config) return;
    const end = config.demo_clock || new Date().toISOString();
    setAsOf(inputDate(end));
    setSince(
      inputDate(new Date(new Date(end).getTime() - 14 * 3600000).toISOString()),
    );
    setWindowStart(
      inputDate(new Date(new Date(end).getTime() - 36 * 3600000).toISOString()),
    );
    const controller = new AbortController();
    api<Encounter[]>(
      `/patients/${encodeURIComponent(patientId)}/encounters`,
      {},
      controller.signal,
    )
      .then((items) => {
        if (context.current !== revision) return;
        setEncounters(items);
        setEncounterId(items[0]?.id || "");
        const previous = runs.find(
          (item) =>
            item.patient_id === patientId &&
            item.encounter_id === items[0]?.id &&
            item.review_status === "accepted",
        );
        if (
          previous &&
          new Date(previous.request.as_of).getTime() <
            new Date(end).getTime() &&
          new Date(previous.request.as_of).getTime() >=
            new Date(end).getTime() - 36 * 3600000
        ) {
          setSince(inputDate(previous.request.as_of));
        }
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [patientId, config]);

  useEffect(() => {
    if (!runId) return;
    const current = context.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await api<Run>(`/runs/${runId}`, {}, controller.signal);
        if (current !== context.current) return;
        setRun(data);
        if (data.status === "queued" || data.status === "running")
          timer = setTimeout(poll, 800);
        else {
          const last = data.reviews?.at(-1);
          setSelected(
            last?.selected_claim_ids ||
              data.snapshot?.claims.map((claim) => claim.id) ||
              [],
          );
          setNote(last?.note || "");
          api<Run[]>("/runs", {}, controller.signal)
            .then(setRuns)
            .catch(() => {});
        }
      } catch (err) {
        if (!controller.signal.aborted) setError((err as Error).message);
      }
    };
    poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    if (!user || page === "workspace") return;
    const controller = new AbortController();
    setError("");
    if (page === "evaluation")
      api<EvalReport>("/evaluation", {}, controller.signal)
        .then(setEvaluation)
        .catch((err) => {
          if (!controller.signal.aborted) setError(err.message);
        });
    if (page === "operations")
      api<Operations>("/operations", {}, controller.signal)
        .then(setOperations)
        .catch((err) => {
          if (!controller.signal.aborted) setError(err.message);
        });
    return () => controller.abort();
  }, [page, user]);

  async function login() {
    setBusy(true);
    setError("");
    try {
      setUser(await api<User>("/session/demo", { method: "POST" }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    const current = context.current;
    setBusy(true);
    setError("");
    setNotice("");
    setEvidence(null);
    setEvidenceId("");
    try {
      const payload = {
        patient_id: patientId,
        encounter_id: encounterId,
        since: new Date(since + "Z").toISOString(),
        as_of: new Date(asOf + "Z").toISOString(),
        window_start: new Date(windowStart + "Z").toISOString(),
        scenario,
      };
      const fingerprint = JSON.stringify(payload);
      const stored = JSON.parse(sessionStorage.getItem("wb_pending") || "null");
      const key =
        stored?.fingerprint === fingerprint ? stored.key : crypto.randomUUID();
      sessionStorage.setItem(
        "wb_pending",
        JSON.stringify({ fingerprint, key }),
      );
      const data = await api<Run>("/runs", {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: fingerprint,
      });
      if (context.current !== current) return;
      setRun(data);
      setRunId(data.id);
      sessionStorage.removeItem("wb_pending");
    } catch (err) {
      if (context.current === current) setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function inspect(id: string) {
    const current = context.current;
    const sequence = ++inspection.current;
    setEvidenceId(id);
    setEvidence(null);
    try {
      const item = await api<Evidence>(`/runs/${runId}/evidence/${id}`);
      if (context.current === current && inspection.current === sequence) {
        setEvidence(item);
        if (window.innerWidth <= 980) {
          requestAnimationFrame(() =>
            document.querySelector(".inspector")?.scrollIntoView({
              behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
                .matches
                ? "instant"
                : "smooth",
              block: "start",
            }),
          );
        }
      }
    } catch (err) {
      if (context.current === current) setError((err as Error).message);
    }
  }

  async function review(accept: boolean) {
    if (!run) return;
    const current = context.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await api<Run>(`/runs/${run.id}/reviews`, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: run.revision,
          selected_claim_ids: selected,
          note,
          accept,
        }),
      });
      if (context.current !== current) return;
      setRun(data);
      setNotice(
        accept
          ? "Handoff accepted. Evidence and review revision are recorded."
          : "Draft revision saved.",
      );
      setRuns(await api<Run[]>("/runs"));
    } catch (err) {
      if (context.current === current) setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function chooseEncounter(value: string) {
    clearSnapshot();
    setEncounterId(value);
  }

  function clearSnapshot() {
    ++context.current;
    setRunId("");
    setRun(null);
    setEvidence(null);
    setEvidenceId("");
    setNote("");
    setSelected([]);
    setNotice("");
  }

  function openRun(item: Run) {
    if (item.id === runId) return;
    ++context.current;
    setRun(null);
    setEvidence(null);
    setEvidenceId("");
    setRunId(item.id);
    setEncounterId(item.encounter_id);
    setNotice("");
  }

  function sources(claim: Claim) {
    return (
      <span className="source-links">
        {claim.evidence_ids.map((id, index) => (
          <button
            key={id}
            className={evidenceId === id ? "source active-source" : "source"}
            onClick={() => inspect(id)}
            aria-label={`Inspect ${claim.kind} source ${index + 1}: ${snapshot?.facts.find((f) => f.evidence_id === id)?.name || id}`}
          >
            <Icon name="file" size={12} />
            {claim.evidence_ids.length > 1
              ? index === 0
                ? "Previous"
                : "Current"
              : "Source"}
          </button>
        ))}
      </span>
    );
  }

  if (!config)
    return (
      <main className="loading-screen">
        <Icon name="pulse" size={32} />
        <p>Connecting to the workbench…</p>
        {error && <p role="alert">{error}</p>}
      </main>
    );

  if (!user)
    return (
      <main className="login-screen">
        <div className="login-mark">
          <Icon name="pulse" size={30} />
          Rounds
        </div>
        <div className="login-content">
          <p className="eyebrow">CLINICAL CHANGE INTELLIGENCE</p>
          <h1>
            Patient review,
            <br />
            with the evidence in view.
          </h1>
          <p>
            Review changes, inspect source records, and prepare a
            clinician-reviewed handoff.
          </p>
          {config.mode === "demo" ? (
            <>
              <button className="primary" onClick={login} disabled={busy}>
                Open synthetic workspace <Icon name="arrow" />
              </button>
              <p className="login-note">
                Three synthetic patients · Fixed replay clock · No API key
                required
              </p>
            </>
          ) : (
            <p>
              Launch this application from your configured SMART sandbox.
              Service clients can use the authenticated API.
            </p>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
        </div>
        <footer>
          Clinical workflow demonstration. Clinical validity has not been
          established.
        </footer>
      </main>
    );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Icon name="pulse" size={25} />
          <strong>Rounds</strong>
        </div>
        <p className="brand-sub">Clinical change workbench</p>
        <nav aria-label="Main navigation">
          {[
            ["workspace", "layers", "Patient review"],
            ["evaluation", "shield", "Evaluation"],
            ["operations", "chart", "Operations"],
          ].map(([key, icon, label]) => (
            <button
              key={key}
              className={page === key ? "nav-item active" : "nav-item"}
              onClick={() => setPage(key)}
            >
              <Icon name={icon} />
              {label}
              {page === key && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="worklist-head">
          <span>YOUR WORKLIST</span>
          <span>{patients.length}</span>
        </div>
        <div className="worklist">
          {patients.map((item) => {
            const latest = runs.find((r) => r.patient_id === item.id);
            return (
              <button
                key={item.id}
                className={`patient-row ${patientId === item.id ? "patient-active" : ""}`}
                onClick={() => {
                  setPatientId(item.id);
                  setPage("workspace");
                }}
              >
                <span className="patient-avatar">
                  {item.name
                    .split(" ")
                    .map((n) => n[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <span>
                  <strong>{item.name}</strong>
                  <small>{item.room}</small>
                  <small className="worklist-status">
                    {latest?.review_status === "accepted"
                      ? "✓ Handoff accepted"
                      : latest?.status === "abstained"
                        ? "Coverage needs review"
                        : item.focus}
                  </small>
                </span>
              </button>
            );
          })}
        </div>
        <div className="sidebar-bottom">
          <div className="environment">
            <span className="live-dot" />
            {config.mode === "demo"
              ? "Synthetic environment"
              : "Authorized FHIR context"}
          </div>
          <small>Evidence-first · Human-reviewed</small>
          <div className="user-row">
            <span className="user-avatar">MP</span>
            <span>
              {user.display_name}
              <small>Review session</small>
            </span>
          </div>
          <button
            className="sign-out"
            onClick={async () => {
              await api("/session/logout", { method: "POST" });
              setUser(null);
              setPatients([]);
              setRuns([]);
              setRun(null);
              setRunId("");
              setEvidence(null);
              setEvidenceId("");
              ++context.current;
            }}
          >
            Sign out
          </button>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="top-breadcrumb">WORKBENCH</span>
            <span className="slash">/</span>
            {page === "workspace"
              ? "Patient review"
              : page === "evaluation"
                ? "Evaluation"
                : "Operations"}
          </div>
          <div className="clock-label">
            <Icon name="clock" size={14} />
            {config.demo_clock
              ? "Replay · " + dateTime(config.demo_clock)
              : "Live FHIR context"}
          </div>
        </header>
        <main className="workspace">
          {error && (
            <div className="message error" role="alert">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="message success" role="status">
              <Icon name="check" />
              {notice}
            </div>
          )}

          {page === "workspace" && (
            <div key={patientId} className="patient-workspace enter">
              <section className="patient-header">
                <div>
                  <p className="eyebrow">PRE-ROUNDING / PATIENT REVIEW</p>
                  <h1>{patient?.name || "Loading worklist…"}</h1>
                  <p className="patient-subtitle">
                    {patient?.room}
                    {patient?.age ? ` · ${patient.age} years` : ""}
                    <span className="divider-dot">·</span>
                    {config.mode === "demo"
                      ? "Synthetic patient"
                      : "Scoped patient context"}
                  </p>
                </div>
                <div className="review-state">
                  {run ? (
                    <>
                      <Status
                        state={
                          run.review_status === "accepted"
                            ? "accepted"
                            : run.status
                        }
                      />
                      <small>
                        Revision {run.revision} · {run.id.slice(0, 8)}
                      </small>
                    </>
                  ) : (
                    <>
                      <span className="review-ready">Ready for review</span>
                      <small>Select an encounter and review window</small>
                    </>
                  )}
                </div>
              </section>

              <section className="controls" aria-label="Briefing settings">
                <label className="encounter-field">
                  Encounter
                  <select
                    value={encounterId}
                    onChange={(event) => chooseEncounter(event.target.value)}
                    disabled={busy}
                  >
                    {encounters.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.id} · {item.status}
                      </option>
                    ))}
                    {!encounters.length && (
                      <option value="">No encounter available</option>
                    )}
                  </select>
                </label>
                <label>
                  Since (UTC)
                  <input
                    aria-label="Since (UTC)"
                    type="datetime-local"
                    value={since}
                    onChange={(event) => {
                      clearSnapshot();
                      setSince(event.target.value);
                    }}
                  />
                </label>
                <label>
                  As of (UTC)
                  <input
                    aria-label="As of (UTC)"
                    type="datetime-local"
                    value={asOf}
                    onChange={(event) => {
                      clearSnapshot();
                      setAsOf(event.target.value);
                    }}
                  />
                </label>
                <button
                  className="primary generate"
                  onClick={generate}
                  disabled={busy || pending || !encounterId || !since || !asOf}
                >
                  {pending ? (
                    <span className="spinner" />
                  ) : (
                    <Icon name="pulse" size={17} />
                  )}{" "}
                  {pending ? "Preparing…" : "Generate briefing"}
                </button>
              </section>
              <details className="advanced">
                <summary>Retrieval window & demo controls</summary>
                <div>
                  <label>
                    Window start (UTC)
                    <input
                      type="datetime-local"
                      value={windowStart}
                      onChange={(event) => {
                        clearSnapshot();
                        setWindowStart(event.target.value);
                      }}
                    />
                  </label>
                  {config.mode === "demo" && (
                    <label>
                      Retrieval scenario
                      <select
                        value={scenario}
                        onChange={(event) => {
                          clearSnapshot();
                          setScenario(event.target.value);
                        }}
                      >
                        <option value="normal">Normal retrieval</option>
                        <option value="outage">
                          Simulate observation outage
                        </option>
                        <option value="denied">Simulate access denial</option>
                      </select>
                    </label>
                  )}
                  <p>
                    Trends compare the latest compatible value on each side of
                    the review boundary.
                  </p>
                </div>
              </details>

              <div className="review-layout">
                <div className="briefing-column">
                  <div className="section-heading">
                    <h2>Review briefing</h2>
                    {snapshot && (
                      <span className="engine-label">
                        <span className="live-dot" />
                        {snapshot.engine.startsWith("llm-ranked")
                          ? snapshot.engine.replace(
                              "llm-ranked:",
                              "LLM-ranked · ",
                            )
                          : snapshot.telemetry.ranking_failed
                            ? "Evidence rules · fallback"
                            : "Evidence rules · no model call"}
                      </span>
                    )}
                  </div>
                  {pending && (
                    <div className="pending-state" role="status">
                      <span className="spinner" />
                      <div>
                        <strong>Preparing an evidence snapshot</strong>
                        <p>
                          Retrieving records, calculating changes, and verifying
                          claims.
                        </p>
                        <button
                          className="text-button"
                          onClick={async () => {
                            await api(`/runs/${runId}/cancel`, {
                              method: "POST",
                            });
                            setRunId("");
                            setRun({ ...run!, status: "cancelled" });
                            setRuns(await api<Run[]>("/runs"));
                          }}
                        >
                          Cancel run
                        </button>
                      </div>
                    </div>
                  )}
                  {!run && (
                    <div className="empty-state">
                      <div className="empty-illustration">
                        <Icon name="layers" size={42} />
                        <span className="evidence-line" />
                        <span className="evidence-line short" />
                      </div>
                      <h3>No briefing for this encounter</h3>
                      <p>
                        Generate a briefing to compare changes, inspect source
                        evidence, and prepare a handoff for this encounter.
                      </p>
                      <span>
                        01 Retrieve <i /> 02 Verify <i /> 03 Review
                      </span>
                    </div>
                  )}
                  {run?.status === "failed" && (
                    <div className="message error">
                      The run failed ({run.error_code}). No briefing was
                      released. Trace: {run.trace_id}
                    </div>
                  )}
                  {run?.status === "cancelled" && (
                    <div className="empty-state">
                      <h3>Run cancelled</h3>
                      <p>No new snapshot was published.</p>
                    </div>
                  )}
                  {snapshot && run && (
                    <>
                      {snapshot.warnings.map((warning) => (
                        <div
                          key={warning}
                          className={
                            snapshot.complete
                              ? "notice-line"
                              : "notice-line incomplete"
                          }
                        >
                          <Icon name="shield" size={16} />
                          <span>{warning}</span>
                        </div>
                      ))}
                      <div className="review-tabs" role="tablist">
                        {[
                          ["briefing", "Briefing"],
                          ["timeline", "Evidence timeline"],
                          ["handoff", "Handoff & revisions"],
                        ].map(([key, label]) => (
                          <button
                            key={key}
                            role="tab"
                            aria-selected={tab === key}
                            className={tab === key ? "selected-tab" : ""}
                            onClick={() => setTab(key)}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      {tab === "briefing" && (
                        <div className="enter">
                          {snapshot.changes.length > 0 && (
                            <section className="changes-section">
                              <div className="section-heading compact">
                                <h3>Changes since review</h3>
                                <span>
                                  {snapshot.changes.length} comparable changes
                                </span>
                              </div>
                              <table className="changes-table">
                                <thead>
                                  <tr>
                                    <th>Measurement</th>
                                    <th>Previous</th>
                                    <th>Current</th>
                                    <th>Change</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {snapshot.changes.map((change) => (
                                    <tr key={change.id}>
                                      <td>
                                        <strong>{change.name}</strong>
                                        <small>{change.unit}</small>
                                      </td>
                                      <td>
                                        <button
                                          onClick={() =>
                                            inspect(change.previous_id)
                                          }
                                        >
                                          {change.previous_value}
                                          <Icon name="file" size={12} />
                                        </button>
                                      </td>
                                      <td>
                                        <button
                                          onClick={() =>
                                            inspect(change.current_id)
                                          }
                                        >
                                          {change.current_value}
                                          <Icon name="file" size={12} />
                                        </button>
                                      </td>
                                      <td className="delta">
                                        {Number(change.delta) > 0 ? "+" : ""}
                                        {change.delta}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              <p className="table-note">
                                Calculated changes describe the record. They do
                                not establish clinical significance.
                              </p>
                            </section>
                          )}
                          <div className="section-heading compact claims-title">
                            <h3>
                              {snapshot.claims.length
                                ? "Evidence-backed statements"
                                : "Briefing withheld"}
                            </h3>
                            <span>{snapshot.claims.length} claims</span>
                          </div>
                          <div className="claim-list">
                            {snapshot.claims.map((claim, index) => (
                              <article
                                className={`claim-row ${selected.includes(claim.id) ? "" : "claim-excluded"}`}
                                key={claim.id}
                              >
                                <label className="claim-select">
                                  <input
                                    aria-label={`Include statement ${index + 1}`}
                                    type="checkbox"
                                    checked={selected.includes(claim.id)}
                                    onChange={() =>
                                      setSelected(
                                        selected.includes(claim.id)
                                          ? selected.filter(
                                              (id) => id !== claim.id,
                                            )
                                          : [...selected, claim.id],
                                      )
                                    }
                                  />
                                  <span className="claim-number">
                                    {String(index + 1).padStart(2, "0")}
                                  </span>
                                </label>
                                <div>
                                  <div className="claim-type">
                                    {claim.kind === "change"
                                      ? "LONGITUDINAL CHANGE"
                                      : "RECORDED EVENT"}
                                    <span>
                                      <Icon name="check" size={12} />
                                      Template verified
                                    </span>
                                  </div>
                                  <p>{claim.text}</p>
                                  {sources(claim)}
                                </div>
                              </article>
                            ))}
                          </div>
                          {!snapshot.claims.length && (
                            <p className="muted padded">
                              Inspect the coverage manifest and available
                              evidence. An incomplete or empty briefing cannot
                              be accepted.
                            </p>
                          )}
                          {snapshot.claims.length > 0 && (
                            <div className="review-actions">
                              <span>
                                <Icon name="shield" size={16} />
                                {selected.length} statements included in handoff
                              </span>
                              <button
                                className="secondary"
                                onClick={() => setTab("handoff")}
                              >
                                Review handoff <Icon name="arrow" size={15} />
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                      {tab === "timeline" && (
                        <section className="timeline enter">
                          <label className="search-field">
                            <Icon name="search" size={15} />
                            <input
                              placeholder="Find evidence by measurement or value"
                              aria-label="Search evidence"
                              value={query}
                              onChange={(event) => setQuery(event.target.value)}
                            />
                          </label>
                          {snapshot.facts
                            .filter((fact) =>
                              `${fact.name} ${fact.value}`
                                .toLowerCase()
                                .includes(query.toLowerCase()),
                            )
                            .map((fact) => (
                              <button
                                key={fact.evidence_id}
                                className="timeline-row"
                                onClick={() => inspect(fact.evidence_id)}
                              >
                                <span className="timeline-marker" />
                                <span>
                                  <strong>{fact.name}</strong>
                                  <small>
                                    {dateTime(fact.timestamp)}{" "}
                                    {fact.date_precision !== "instant"
                                      ? "· imprecise date"
                                      : ""}
                                  </small>
                                </span>
                                <span className="timeline-value">
                                  {fact.value} {fact.unit}
                                  <small>
                                    {fact.stale
                                      ? "Historical · >12h"
                                      : fact.status}
                                  </small>
                                </span>
                                <Icon name="file" size={15} />
                              </button>
                            ))}
                        </section>
                      )}
                      {tab === "handoff" && (
                        <section className="handoff enter">
                          <div className="section-heading compact">
                            <h3>Handoff draft</h3>
                            <Status state={run.review_status} />
                          </div>
                          <p className="muted">
                            Selected statements retain their original evidence.
                            Notes are clinician-authored and are not
                            automatically verified.
                          </p>
                          <ol className="handoff-list">
                            {snapshot.claims
                              .filter((claim) => selected.includes(claim.id))
                              .map((claim) => (
                                <li key={claim.id}>
                                  {claim.text}
                                  {sources(claim)}
                                </li>
                              ))}
                          </ol>
                          <label className="note-label">
                            Clinician note
                            <textarea
                              placeholder="Add review context or explain excluded statements…"
                              value={note}
                              onChange={(event) => setNote(event.target.value)}
                              maxLength={5000}
                              rows={4}
                            />
                          </label>
                          <div className="handoff-actions">
                            <button
                              className="secondary"
                              onClick={() => review(false)}
                              disabled={busy}
                            >
                              Save draft
                            </button>
                            <button
                              className="primary"
                              onClick={() => review(true)}
                              disabled={
                                busy || !snapshot.complete || !selected.length
                              }
                            >
                              <Icon name="check" size={16} />
                              Accept handoff
                            </button>
                          </div>
                          <div className="revision-list">
                            <h3>Review history</h3>
                            {!run.reviews?.length && (
                              <p className="muted">No review revisions yet.</p>
                            )}
                            {run.reviews
                              ?.slice()
                              .reverse()
                              .map((item) => (
                                <div
                                  key={item.revision}
                                  className="revision-row"
                                >
                                  <Icon name="file" size={17} />
                                  <div>
                                    <strong>
                                      Revision {item.revision} · {item.status}
                                    </strong>
                                    <small>
                                      {item.actor_id} ·{" "}
                                      {dateTime(item.created_at)}
                                    </small>
                                    {item.note && <p>{item.note}</p>}
                                    <code>
                                      Evidence {item.snapshot_hash.slice(0, 16)}
                                    </code>
                                  </div>
                                </div>
                              ))}
                          </div>
                        </section>
                      )}
                      <footer className="snapshot-footer">
                        <Icon name="shield" size={14} />
                        <span>
                          Snapshot{" "}
                          <code>{snapshot.snapshot_hash.slice(0, 16)}</code>
                        </span>
                        <span>
                          {snapshot.facts.length} facts ·{" "}
                          {dateTime(snapshot.as_of)}
                        </span>
                      </footer>
                    </>
                  )}
                  <section className="recent-runs">
                    <div className="section-heading compact">
                      <h3>Recent briefings</h3>
                      <span>This patient</span>
                    </div>
                    {runs
                      .filter(
                        (item) =>
                          item.patient_id === patientId &&
                          item.encounter_id === encounterId,
                      )
                      .slice(0, 6)
                      .map((item) => (
                        <button
                          key={item.id}
                          onClick={() => openRun(item)}
                          className={
                            runId === item.id ? "run-row active-run" : "run-row"
                          }
                        >
                          <Icon name="file" size={16} />
                          <span>
                            {dateTime(item.request.as_of)}
                            <small>
                              {item.id.slice(0, 8)} · revision {item.revision}
                            </small>
                          </span>
                          <Status
                            state={
                              item.review_status === "accepted"
                                ? "accepted"
                                : item.status
                            }
                          />
                          <Icon name="arrow" size={15} />
                        </button>
                      ))}
                    {!runs.some(
                      (item) =>
                        item.patient_id === patientId &&
                        item.encounter_id === encounterId,
                    ) && (
                      <p className="muted">
                        No saved briefings for this encounter.
                      </p>
                    )}
                  </section>
                </div>

                <aside className="inspector" aria-label="Evidence inspector">
                  <div className="section-heading">
                    <h2>
                      {evidenceId ? "Source evidence" : "Retrieval coverage"}
                    </h2>
                    {evidenceId && (
                      <button
                        className="icon-button"
                        aria-label="Close evidence"
                        onClick={() => {
                          setEvidenceId("");
                          setEvidence(null);
                        }}
                      >
                        <Icon name="close" size={16} />
                      </button>
                    )}
                  </div>
                  {evidenceId ? (
                    evidence ? (
                      <div className="evidence-detail enter">
                        <p className="eyebrow">IMMUTABLE SOURCE SNAPSHOT</p>
                        <h3>{evidence.fact.name}</h3>
                        <div className="source-value">
                          {evidence.fact.value}
                          <span>{evidence.fact.unit}</span>
                        </div>
                        <dl>
                          <div>
                            <dt>Event time</dt>
                            <dd>{dateTime(evidence.fact.timestamp)}</dd>
                          </div>
                          <div>
                            <dt>Resource version</dt>
                            <dd>{evidence.fact.version}</dd>
                          </div>
                          <div>
                            <dt>Source status</dt>
                            <dd>{evidence.fact.status}</dd>
                          </div>
                          <div>
                            <dt>Value path</dt>
                            <dd>
                              <code>{evidence.fact.path}</code>
                            </dd>
                          </div>
                        </dl>
                        <p className="resource-key">
                          {evidence.fact.resource_key}
                        </p>
                        <details open>
                          <summary>Raw FHIR resource</summary>
                          <pre>
                            {JSON.stringify(evidence.resource, null, 2)}
                          </pre>
                        </details>
                        <div className="hash-note">
                          <Icon name="shield" size={14} />
                          <span>
                            SHA-256 content fingerprint
                            <code>{evidence.fact.resource_hash}</code>
                          </span>
                        </div>
                      </div>
                    ) : (
                      <p className="muted">Loading source record…</p>
                    )
                  ) : (
                    <>
                      <p className="inspector-intro">
                        Coverage is recorded separately from clinical findings.
                      </p>
                      {snapshot ? (
                        <>
                          <div
                            className={`coverage-summary ${snapshot.complete ? "" : "coverage-incomplete"}`}
                          >
                            <Icon name="shield" size={20} />
                            <div>
                              <strong>
                                {snapshot.complete
                                  ? "Required retrieval complete"
                                  : "Coverage incomplete"}
                              </strong>
                              <small>
                                {snapshot.complete
                                  ? "Review scope: observations and medications"
                                  : "Briefing withheld pending evidence review"}
                              </small>
                            </div>
                          </div>
                          <div className="coverage-list">
                            {snapshot.manifest.map((item) => (
                              <div
                                key={item.resource_type}
                                className="coverage-row"
                              >
                                <div>
                                  <strong>
                                    {item.resource_type.replace(
                                      "Medication",
                                      "Medication ",
                                    )}
                                  </strong>
                                  <Status state={item.state} />
                                </div>
                                <small>
                                  {item.reason ||
                                    `${item.count} retrieved · ${item.excluded} excluded`}
                                  {item.unknown_dates
                                    ? ` · ${item.unknown_dates} unknown dates`
                                    : ""}
                                </small>
                              </div>
                            ))}
                          </div>
                          <p className="inspector-note">
                            “Not queried” means outside this briefing's scope.
                            Empty retrieval does not establish that a clinical
                            event never occurred.
                          </p>
                        </>
                      ) : (
                        <div className="coverage-placeholder">
                          <Icon name="shield" size={28} />
                          <h3>Retrieval manifest</h3>
                          <p>
                            Every run records available, empty, unavailable, and
                            access-denied sources.
                          </p>
                          <ul>
                            <li>Observations</li>
                            <li>Medication requests</li>
                            <li>Medication administrations</li>
                          </ul>
                        </div>
                      )}
                      <div className="inspector-bottom">
                        <Icon name="file" size={18} />
                        <p>
                          Open a source beside any statement to inspect its
                          exact record, version, and content fingerprint.
                        </p>
                      </div>
                    </>
                  )}
                </aside>
              </div>
            </div>
          )}

          {page === "evaluation" && (
            <section className="report-page enter">
              <p className="eyebrow">QUALITY / REPRODUCIBLE FIXTURES</p>
              <h1>Evaluation results</h1>
              <p className="page-description">
                Versioned engineering scenarios for temporal logic, missingness,
                citations, and abstention.
              </p>
              {evaluation ? (
                <>
                  <div className="report-strip">
                    <div>
                      <small>Scenario agreement</small>
                      <strong>
                        {evaluation.metrics.case_pass_rate.numerator}
                        <span>
                          {" "}
                          / {evaluation.metrics.case_pass_rate.denominator}
                        </span>
                      </strong>
                    </div>
                    <div>
                      <small>Citation references resolve</small>
                      <strong>
                        {
                          evaluation.metrics.citation_reference_validity
                            .numerator
                        }
                        <span>
                          {" "}
                          /{" "}
                          {
                            evaluation.metrics.citation_reference_validity
                              .denominator
                          }
                        </span>
                      </strong>
                    </div>
                    <div>
                      <small>Dataset</small>
                      <code>{evaluation.dataset_version}</code>
                      <small>{evaluation.pipeline_version}</small>
                    </div>
                  </div>
                  <table className="report-table">
                    <thead>
                      <tr>
                        <th>Scenario</th>
                        <th>Expected</th>
                        <th>Actual</th>
                        <th>Claims</th>
                        <th>Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluation.cases.map((item) => (
                        <tr key={item.case_id}>
                          <td>{item.case_id.replaceAll("-", " ")}</td>
                          <td>{item.expected_state}</td>
                          <td>{item.actual_state}</td>
                          <td>{item.claim_count}</td>
                          <td>
                            <Status state={item.passed ? "passed" : "failed"} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="limitations">
                    <h3>What these results establish</h3>
                    {evaluation.limitations.map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                    <p>
                      Template checks measure agreement with extracted evidence.
                      Clinical quality and model prioritization require separate
                      evaluation.
                    </p>
                  </div>
                </>
              ) : (
                <p>Running synthetic checks…</p>
              )}
            </section>
          )}

          {page === "operations" && (
            <section className="report-page enter">
              <p className="eyebrow">OPERATIONS / CURRENT PRINCIPAL</p>
              <h1>Run health & access history</h1>
              <p className="page-description">
                {operations?.scope || "Loading operational data…"}
              </p>
              {operations && (
                <>
                  <div className="report-strip">
                    <div>
                      <small>Runs</small>
                      <strong>{operations.total_runs}</strong>
                    </div>
                    <div>
                      <small>Withheld</small>
                      <strong>{operations.abstained}</strong>
                    </div>
                    <div>
                      <small>Accepted</small>
                      <strong>{operations.accepted}</strong>
                    </div>
                    <div>
                      <small>p95 processing</small>
                      <strong>
                        {operations.p95_ms !== null
                          ? Math.round(operations.p95_ms)
                          : "—"}
                        <span> ms</span>
                      </strong>
                    </div>
                  </div>
                  <div className="ops-context">
                    <span>{operations.total_tokens} model tokens</span>
                    <span>
                      {operations.cost_usd === null
                        ? "Estimated cost unavailable"
                        : `Estimated model cost: $${operations.cost_usd.toFixed(4)}`}
                    </span>
                    <span>{operations.failed} failed runs</span>
                    <span>{operations.cost_note}</span>
                  </div>
                  <div className="section-heading">
                    <h2>Access & review events</h2>
                    <span>Latest 50</span>
                  </div>
                  <table className="report-table">
                    <thead>
                      <tr>
                        <th>Event</th>
                        <th>Time</th>
                        <th>Outcome</th>
                        <th>Trace</th>
                      </tr>
                    </thead>
                    <tbody>
                      {operations.events.map((event, index) => (
                        <tr key={index}>
                          <td>{event.action}</td>
                          <td>{dateTime(event.created_at)}</td>
                          <td>
                            <Status state={event.outcome} />
                          </td>
                          <td>
                            <code>{event.trace_id.slice(0, 12)}</code>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </section>
          )}
        </main>
        <footer className="app-footer">
          {config.mode === "demo"
            ? "SYNTHETIC DATA ONLY"
            : "SCOPED FHIR WORKSPACE"}
          <span>
            Clinician review required · Clinical validity has not been
            established
          </span>
          <span>Rounds</span>
        </footer>
      </div>
    </div>
  );
}
