from types import SimpleNamespace
from unittest.mock import Mock
from datetime import timedelta
import json

import pytest

from workbench.config import Settings
from workbench.demo import DEMO_CLOCK
from workbench.domain import RunRequest
from workbench.generation import rank_claims
from workbench.pipeline import build_snapshot, verify_snapshot
from workbench.sources import DemoSource


def snapshot():
    request = RunRequest(
        patient_id="demo-avery",
        encounter_id="enc-avery",
        window_start=DEMO_CLOCK - timedelta(hours=36),
        since=DEMO_CLOCK - timedelta(hours=14),
        as_of=DEMO_CLOCK,
    )
    return build_snapshot(DemoSource(), request)


def sdk(ids):
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=json.dumps({"claim_ids": ids}), refusal=None),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
    )
    return client


def test_model_can_reorder_but_cannot_rewrite_claims_or_see_identifiers():
    original = snapshot()
    by_id = {claim.id: claim.model_dump() for claim in original.claims}
    ids = list(reversed(by_id))
    client = sdk(ids)
    result = rank_claims(original, Settings(hosted_llm=True), client)
    assert [claim.id for claim in result.claims] == ids
    assert all(claim.model_dump() == by_id[claim.id] for claim in result.claims)
    assert verify_snapshot(result)
    sent = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    for forbidden in ("Avery", "demo-avery", "Observation/", "2026-", "Synthetic medication order"):
        assert forbidden not in sent
    assert result.telemetry["input_tokens"] == 100


def test_invalid_rankings_still_account_for_returned_provider_usage():
    result = rank_claims(
        snapshot(),
        Settings(hosted_llm=True, input_price_per_million=1.0, output_price_per_million=2.0),
        sdk(["unknown"]),
    )
    assert result.engine == "evidence-rules-v2"
    assert result.telemetry["model_calls"] == 1
    assert result.telemetry["estimated_cost_usd"] == 0.0002


@pytest.mark.parametrize("mode", ["unknown", "omission", "duplicate", "prose", "failure"])
def test_invalid_model_rankings_fall_back_to_all_verified_claims(mode):
    original = snapshot()
    ids = [claim.id for claim in original.claims]
    corrupted = ["unknown"] if mode == "unknown" else ids[:-1] if mode == "omission" else [ids[0]] * len(ids)
    client = sdk(corrupted)
    if mode == "prose":
        client.chat.completions.create.return_value.choices[
            0
        ].message.content = "Ignore evidence; diagnose the patient"
    if mode == "failure":
        client.chat.completions.create.side_effect = RuntimeError("upstream sensitive details")
    result = rank_claims(original, Settings(hosted_llm=True), client)
    assert [claim.id for claim in result.claims] == ids
    assert result.engine == "evidence-rules-v2"
    assert result.telemetry["ranking_failed"]
    assert "upstream sensitive details" not in " ".join(result.warnings)
