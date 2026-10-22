from openai import OpenAI
import os
import logging

logger = logging.getLogger(__name__)

class LLMGenerationError(RuntimeError):
    """Generation failed; no summary should be displayed or audited as successful."""

class LLMClient:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not found. LLM calls will fail unless a local base_url is used without auth.")
        
        if not self.api_key and not base_url:
            raise LLMGenerationError("Set OPENAI_API_KEY before generating a summary.")
        self.client = OpenAI(
            api_key=self.api_key or "local-no-auth",
            base_url=base_url,
            timeout=60.0,
            max_retries=2,
        )
        self.model = model

    def generate_summary(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generates a summary using the LLM.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0
            )
            message = response.choices[0].message
            if getattr(message, "refusal", None) or not message.content or not message.content.strip():
                raise LLMGenerationError("The model did not return a summary. Please retry.")
            if response.choices[0].finish_reason != "stop":
                raise LLMGenerationError("The model returned an incomplete summary. Please retry.")
            return message.content
        except LLMGenerationError:
            raise
        except Exception as e:
            logger.error("LLM generation failed (%s)", type(e).__name__)
            raise LLMGenerationError("Summary generation failed. Check the model service and API configuration.") from e
