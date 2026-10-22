export type Patient = {
  id: string;
  name: string;
  room: string;
  age?: number;
  focus: string;
  encounter_id?: string;
};
export type Encounter = {
  id: string;
  status: string;
  period: { start?: string; end?: string };
};
export type Config = {
  mode: "demo" | "fhir";
  demo_clock: string | null;
  smart_enabled: boolean;
  hosted_ranking: boolean;
  version: string;
  session_active: boolean;
};
export type User = {
  actor_id: string;
  display_name: string;
  patient_ids: string[];
};
export type Fact = {
  evidence_id: string;
  resource_key: string;
  version: string;
  path: string;
  kind: string;
  name: string;
  value: string;
  unit: string | null;
  timestamp: string | null;
  date_precision: string;
  status: string;
  stale: boolean;
  resource_hash: string;
};
export type Claim = {
  id: string;
  kind: string;
  text: string;
  evidence_ids: string[];
  validation: string;
};
export type Change = {
  id: string;
  name: string;
  previous_id: string;
  current_id: string;
  previous_value: string;
  current_value: string;
  delta: string;
  unit: string;
  direction: string;
};
export type Coverage = {
  resource_type: string;
  state: string;
  count: number;
  reason: string;
  excluded: number;
  unknown_dates: number;
  stale_count: number;
};
export type Snapshot = {
  patient_id: string;
  encounter_id: string;
  window_start: string;
  since: string;
  as_of: string;
  complete: boolean;
  snapshot_hash: string;
  engine: string;
  facts: Fact[];
  changes: Change[];
  claims: Claim[];
  manifest: Coverage[];
  warnings: string[];
  telemetry: Record<string, number | boolean | null>;
};
export type Review = {
  revision: number;
  actor_id: string;
  note: string;
  status: string;
  selected_claim_ids: string[];
  snapshot_hash: string;
  created_at: string;
};
export type Run = {
  id: string;
  patient_id: string;
  encounter_id: string;
  status: string;
  revision: number;
  review_status: string;
  created_at: string;
  updated_at: string;
  error_code?: string;
  trace_id: string;
  snapshot?: Snapshot | null;
  reviews?: Review[];
  request: { since: string; as_of: string; window_start: string };
};
export type Evidence = {
  fact: Fact;
  resource: Record<string, unknown>;
  snapshot_hash: string;
};
export type EvalReport = {
  dataset_version: string;
  description: string;
  pipeline_version: string;
  prompt_version: string;
  limitations: string[];
  metrics: Record<
    string,
    { numerator: number; denominator: number; value: number | null }
  >;
  cases: {
    case_id: string;
    passed: boolean;
    expected_state: string;
    actual_state: string;
    claim_count: number;
    latency_ms: number;
  }[];
};
export type Operations = {
  cost_usd: number | null;
  scope: string;
  total_runs: number;
  completed: number;
  abstained: number;
  failed: number;
  accepted: number;
  p95_ms: number | null;
  total_tokens: number;
  cost_note: string;
  events: {
    action: string;
    outcome: string;
    created_at: string;
    trace_id: string;
  }[];
};
