"""watsonx LLM client — shared infrastructure for all agents.

Provides the low-level call_watsonx_raw() function, concurrency semaphore,
and circuit breaker used by BaseAgent and its subclasses.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Concurrency limiter for watsonx API calls
_semaphore = asyncio.Semaphore(5)

# Circuit breaker: skip watsonx after first auth/connection failure
_watsonx_disabled = False


async def call_watsonx_raw(
    system_prompt: str,
    user_prompt: str,
    model_id: str = "meta-llama/llama-3-3-70b-instruct",
    max_tokens: int = 500,
    temperature: float = 0.1,
) -> str:
    """Low-level WatsonX call returning raw text. Raises on failure."""

    def _sync_call() -> str:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        creds = Credentials(
            url=settings.watsonx_url,
            api_key=settings.watsonx_api_key,
        )
        model = ModelInference(
            model_id=model_id,
            credentials=creds,
            project_id=settings.watsonx_project_id,
            params={
                "decoding_method": "greedy",
                "max_new_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        return model.generate_text(
            prompt=f"{system_prompt}\n\nUser: {user_prompt}\nAssistant:"
        )

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_call)
