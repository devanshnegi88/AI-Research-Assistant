"""
Planner agent node functions.

Each node takes the current `PlannerState` and returns a partial dict —
LangGraph merges it into the running state (standard `StateGraph` node
contract). `route_after_intent` is the conditional-edge function that
decides which node runs next based on classified intent.

Every LLM call here uses json_mode + low temperature, and every parse has
a fallback: if the model's output isn't valid JSON or doesn't match the
expected shape, we default to the safest behavior (treat as a normal
document question) rather than failing the whole turn. Planning is an
optimization over "just do RAG" — it should never be a single point of
failure for it.
"""

from __future__ import annotations

import json

from app.agents.prompts import (
    DIRECT_RESPONSE_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    TASK_DECOMPOSITION_PROMPT,
)
from app.agents.state import PlannerState
from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import MessageRole
from app.schemas.agent import ExecutionPlan, Intent, SubTask
from app.services.rag.llm_client import LLMClient

logger = get_logger(__name__)


def _history_block(state: PlannerState) -> str:
    parts = []
    if state.get("history_summary"):
        parts.append(f"Summary of earlier conversation:\n{state['history_summary']}")
    history_messages = state.get("history_messages") or []
    if history_messages:
        transcript = "\n".join(
            f"{'User' if m.role == MessageRole.USER else 'Assistant'}: {m.content}"
            for m in history_messages
        )
        parts.append(f"Recent conversation:\n{transcript}")
    return ("\n\n".join(parts) + "\n\n") if parts else ""


class PlannerNodes:
    """Bound to an LLMClient so nodes are plain async functions LangGraph
    can call directly, without needing their own DI resolution."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    async def classify_intent(self, state: PlannerState) -> dict:
        prompt = f"{_history_block(state)}Message to classify: {state['message']}"

        try:
            raw = await self.llm_client.generate(
                INTENT_CLASSIFICATION_PROMPT,
                prompt,
                json_mode=True,
                temperature=settings.PLANNER_TEMPERATURE,
            )
            parsed = json.loads(raw)
            intent = Intent(parsed["intent"])
        except Exception as exc:  # noqa: BLE001 — any parse/validation failure
            logger.warning(
                "intent_classification_fallback",
                extra={"error": str(exc)},
            )
            # Fail open into the default, most-capable path rather than
            # failing the turn — worst case, retrieval finds nothing and
            # RAGService's own no-context handling takes over from there.
            intent = Intent.DOCUMENT_QUESTION

        return {"intent": intent}

    async def decompose_tasks(self, state: PlannerState) -> dict:
        prompt = f"{_history_block(state)}Question to decompose: {state['message']}"
        # .replace(), not .format() — the prompt's own JSON examples
        # contain literal { } that .format() would misread as placeholders.
        system_prompt = TASK_DECOMPOSITION_PROMPT.replace(
            "{max_subtasks}", str(settings.PLANNER_MAX_SUBTASKS)
        )

        try:
            raw = await self.llm_client.generate(
                system_prompt,
                prompt,
                json_mode=True,
                temperature=settings.PLANNER_TEMPERATURE,
            )
            parsed = json.loads(raw)
            subtasks = [SubTask(query=t["query"]) for t in parsed["subtasks"]]
            if not subtasks:
                raise ValueError("decomposition returned zero subtasks")
            subtasks = subtasks[: settings.PLANNER_MAX_SUBTASKS]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "task_decomposition_fallback",
                extra={"error": str(exc)},
            )
            # Fall back to a single subtask using the raw message verbatim
            # — equivalent to Phase 4's behavior before the planner existed.
            subtasks = [SubTask(query=state["message"])]

        return {"subtasks": subtasks}

    async def generate_direct_response(self, state: PlannerState) -> dict:
        prompt = f"{_history_block(state)}Message: {state['message']}"
        try:
            response = await self.llm_client.generate(
                DIRECT_RESPONSE_PROMPT,
                prompt,
                temperature=settings.RAG_TEMPERATURE,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("direct_response_fallback", extra={"error": str(exc)})
            response = "Could you clarify what you'd like help with?"

        return {"direct_response": response}

    async def finalize(self, state: PlannerState) -> dict:
        plan = ExecutionPlan(
            intent=state["intent"],
            subtasks=state.get("subtasks", []),
            direct_response=state.get("direct_response"),
        )
        return {"plan": plan}


def route_after_intent(state: PlannerState) -> str:
    """Conditional edge — LangGraph calls this after classify_intent to
    decide which node runs next."""
    if state["intent"] == Intent.DOCUMENT_QUESTION:
        return "decompose_tasks"
    return "generate_direct_response"