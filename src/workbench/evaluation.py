import argparse
from datetime import timedelta
import json
from pathlib import Path
from time import perf_counter

from .config import ROOT
from .demo import DEMO_CLOCK, PATIENTS
from .domain import RunRequest, utcnow
from .pipeline import build_snapshot, verify_snapshot
from .sources import DemoSource


def evaluate():
    dataset = json.loads((ROOT / "data" / "evaluation" / "cases.json").read_text(encoding="utf-8"))
    results, reference_total, verified_total = [], 0, 0
    for case in dataset["cases"]:
        patient = next(p for p in PATIENTS if p["id"] == case["patient_id"])
        request = RunRequest(
            patient_id=patient["id"],
            encounter_id=patient["encounter_id"],
            window_start=DEMO_CLOCK - timedelta(hours=36),
            since=DEMO_CLOCK - timedelta(hours=14),
            as_of=DEMO_CLOCK,
            scenario=case["scenario"],
        )
        started = perf_counter()
        snapshot = build_snapshot(DemoSource(), request)
        elapsed = round((perf_counter() - started) * 1000, 3)
        state = "completed" if snapshot.complete and snapshot.claims else "abstained"
        deltas = {change.name: change.delta for change in snapshot.changes}
        valid = verify_snapshot(snapshot)
        evidence_ids = {fact.evidence_id for fact in snapshot.facts}
        references = [eid for claim in snapshot.claims for eid in claim.evidence_ids]
        reference_total += len(references)
        verified_total += sum(eid in evidence_ids for eid in references)
        passed = state == case["expected_state"] and deltas == case["expected_changes"] and valid
        results.append(
            {
                "case_id": case["id"],
                "passed": passed,
                "expected_state": case["expected_state"],
                "actual_state": state,
                "expected_changes": case["expected_changes"],
                "actual_changes": deltas,
                "claim_count": len(snapshot.claims),
                "latency_ms": elapsed,
                "snapshot_hash": snapshot.snapshot_hash,
            }
        )
    passed = sum(case["passed"] for case in results)
    return {
        "dataset_version": dataset["dataset_version"],
        "description": dataset["description"],
        "pipeline_version": "evidence-rules-v2",
        "prompt_version": "rank-claims-v1",
        "generated_at": utcnow().isoformat(),
        "model_calls": 0,
        "metrics": {
            "case_pass_rate": {
                "numerator": passed,
                "denominator": len(results),
                "value": passed / len(results),
            },
            "citation_reference_validity": {
                "numerator": verified_total,
                "denominator": reference_total,
                "value": verified_total / reference_total if reference_total else None,
            },
        },
        "limitations": [
            "Synthetic fixtures only; no clinician-adjudicated clinical quality results.",
            "Measures deterministic pipeline behavior, not LLM salience quality or clinical benefit.",
            "Template verification establishes agreement with extracted evidence, not correctness of the EHR record.",
        ],
        "cases": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Reproducible v2 engineering evaluation")
    parser.add_argument("--output", type=Path, default=ROOT / ".local" / "evaluation.json")
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    report = evaluate()
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        if baseline["dataset_version"] != report["dataset_version"]:
            raise ValueError("Baseline dataset versions differ")
        report["comparison"] = {
            "baseline_pipeline": baseline["pipeline_version"],
            "candidate_pipeline": report["pipeline_version"],
            "case_pass_rate_delta": report["metrics"]["case_pass_rate"]["value"]
            - baseline["metrics"]["case_pass_rate"]["value"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "metrics": report["metrics"]}, indent=2))
    if not all(case["passed"] for case in report["cases"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
