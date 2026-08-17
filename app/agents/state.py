"""
Planner agent state — the dict LangGraph threads through every node.

Kept as a plain TypedDict (LangGraph's standard pattern) rather than a
Pydantic model — nodes return partial dict updates that LangGraph merges
into the running state, which is how `StateGraph` is designed to be used.
"""

from __future__ import annotations

from typing import TypedDict

from app.models.conversation import Message
from app.schemas.agent import ExecutionPlan, Intent, SubTask


class PlannerState(TypedDict, total=False):
    # --- Input (set before the graph runs, never mutated by nodes) ---
    message: str
    history_summary: str | None
    history_messages: list[Message]

    # --- Populated by classify_intent ---
    intent: Intent

    # --- Populated by decompose_tasks (only reached for DOCUMENT_QUESTION) ---
    subtasks: list[SubTask]

    # --- Populated by the direct-response nodes (chitchat / clarification /
    # out-of-scope) — bypasses retrieval entirely ---
    direct_response: str | None

    # --- Final output, populated by finalize ---
    plan: ExecutionPlan