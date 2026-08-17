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
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        """Generate a completion. Raises `LLMGenerationException` on failure.

        `json_mode` requests the provider's structured-output mode where
        available (Gemini: `response_mime_type="application/json"`) — the
        caller is still responsible for parsing and validating the result;
        this is a hint to the provider, not a guarantee of valid JSON.
        `temperature` overrides the default (RAG_TEMPERATURE) for this
        call only — planner nodes want near-zero temperature for
        classification/routing, which is a different concern from answer
        generation.
        """


class GeminiLLMClient(LLMClient):
    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise LLMGenerationException(
                "GEMINI_API_KEY is not configured — set it in .env to use chat/RAG"
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._model_name = settings.GEMINI_MODEL_NAME

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )
        generation_config = genai.types.GenerationConfig(
            temperature=temperature if temperature is not None else settings.RAG_TEMPERATURE,
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        try:
            response = await model.generate_content_async(
                user_prompt,
                generation_config=generation_config,
            )
        except Exception as exc:  # noqa: BLE001 — provider SDK raises its own types
            raise LLMGenerationException(f"Gemini generation failed: {exc}") from exc

        if not response.text:
            raise LLMGenerationException("Gemini returned an empty response")

        return response.text


def get_llm_client() -> LLMClient:
    return GeminiLLMClient()