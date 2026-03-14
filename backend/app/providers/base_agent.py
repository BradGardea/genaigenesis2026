"""Generic base agent backed by WatsonX.

Subclasses provide a system prompt, prompt builder, output parser, and
rule-based fallback.  The shared infrastructure (semaphore, circuit breaker,
timeout) lives here.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from app.core.config import settings
from app.providers.watsonx_client import _semaphore, _watsonx_disabled, call_watsonx_raw

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseAgent(ABC, Generic[T]):
    agent_name: str = "base"
    system_prompt: str = ""
    model_id: str = "meta-llama/llama-3-3-70b-instruct"
    max_tokens: int = 500
    temperature: float = 0.1

    @abstractmethod
    def build_user_prompt(self, context: dict) -> str:
        """Build the user-facing prompt from a context dict."""

    @abstractmethod
    def parse_response(self, raw_text: str) -> T | None:
        """Parse raw LLM text into the typed output. Return None on failure."""

    @abstractmethod
    def fallback(self, context: dict) -> T:
        """Deterministic rule-based fallback when LLM is unavailable."""

    async def run(self, context: dict) -> T:
        """Execute the agent: LLM call with fallback on failure."""
        import app.providers.watsonx_client as _mod

        if not settings.watsonx_api_key or _mod._watsonx_disabled:
            logger.info("%s: no credentials or breaker tripped — using fallback", self.agent_name)
            return self.fallback(context)

        async with _semaphore:
            if _mod._watsonx_disabled:
                return self.fallback(context)
            try:
                raw = await asyncio.wait_for(
                    call_watsonx_raw(
                        system_prompt=self.system_prompt,
                        user_prompt=self.build_user_prompt(context),
                        model_id=self.model_id,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    ),
                    timeout=10.0,
                )
                result = self.parse_response(raw)
                if result is None:
                    logger.warning("%s: parse failed, raw=%s", self.agent_name, raw[:300])
                    return self.fallback(context)
                return result
            except Exception:
                logger.warning("%s: watsonx call failed — tripping breaker", self.agent_name, exc_info=True)
                _mod._watsonx_disabled = True
                return self.fallback(context)
