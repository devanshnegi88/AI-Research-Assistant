"""
LLM client interface + Gemini implementation.

Kept behind an interface so the RAG service never depends on a specific
provider's SDK — swapping Gemini for another provider (Anthropic, OpenAI,
a local model via Ollama) is a new class here, nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import google.generativeai as genai

from app.core.config import settings
from app.core.exceptions import AppException


class LLMGenerationException(AppException):
    """The LLM provider failed to generate a response."""

    status_code = 502
    error_code = "llm_generation_failed"


class LLMClient(ABC):
    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate a completion. Raises `LLMGenerationException` on failure."""


class GeminiLLMClient(LLMClient):
    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise LLMGenerationException(
                "GEMINI_API_KEY is not configured — set it in .env to use chat/RAG"
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model_name = settings.GEMINI_MODEL_NAME

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )
        try:
            response = await model.generate_content_async(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=settings.RAG_TEMPERATURE,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — provider SDK raises its own types
            raise LLMGenerationException(f"Gemini generation failed: {exc}") from exc

        if not response.text:
            raise LLMGenerationException("Gemini returned an empty response")

        return response.text


def get_llm_client() -> LLMClient:
    return GeminiLLMClient()