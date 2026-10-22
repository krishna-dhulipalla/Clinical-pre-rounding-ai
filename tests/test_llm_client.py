from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from llm import client


@pytest.mark.parametrize("content,finish_reason,refusal", [
    (None, "stop", None), (" ", "stop", None),
    ("Partial summary", "length", None), ("Refused", "stop", "refusal"),
])
def test_invalid_model_response_is_an_error(monkeypatch, content, finish_reason, refusal):
    sdk = Mock()
    sdk.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content, refusal=refusal), finish_reason=finish_reason,
    )])
    monkeypatch.setattr(client, "OpenAI", Mock(return_value=sdk))
    with pytest.raises(client.LLMGenerationError):
        client.LLMClient(api_key="test-key").generate_summary("system", "facts")


def test_api_failure_is_not_returned_as_summary_text(monkeypatch):
    sdk = Mock()
    sdk.chat.completions.create.side_effect = RuntimeError("sensitive upstream details")
    monkeypatch.setattr(client, "OpenAI", Mock(return_value=sdk))
    with pytest.raises(client.LLMGenerationError, match="Summary generation failed") as exc:
        client.LLMClient(api_key="test-key").generate_summary("system", "facts")
    assert "sensitive" not in str(exc.value)
