"""
Planner agent DTOs.

These are both the LangGraph node output contract (what the planner LLM is
asked to produce as JSON) and what gets surfaced back to the API caller for
transparency into what the agent decided.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from app.schemas.search import SearchFilters


class Intent(str, enum.Enum):
    """What kind of message this is — drives the planner's routing."""

    DOCUMENT_QUESTION = "document_question"  # needs retrieval from the user's documents
    CHITCHAT = "chitchat"  # greeting, thanks, small talk — no retrieval needed
    CLARIFICATION_NEEDED = "clarification_needed"  # too ambiguous to plan retrieval for
    OUT_OF_SCOPE = "out_of_scope"  # not answerable from documents and not chitchat


class RetrievalStrategy(str, enum.Enum):
    """How a subtask should be retrieved — currently informational; all
    strategies use the same HybridRetriever today, but this is the seam
    for e.g. a future "SUMMARY_OVER_DOCUMENT" strategy that bypasses
    chunk-level search entirely."""

    HYBRID_SEARCH = "hybrid_search"
    NONE = "none"  # answerable from conversation history/summary alone


class SubTask(BaseModel):
    """One decomposed piece of a (possibly complex) user question."""

    query: str = Field(min_length=1, description="Self-contained search query for this subtask")
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID_SEARCH
    filters: SearchFilters | None = None


class ExecutionPlan(BaseModel):
    """The planner's final decision for a single `/chat` turn."""

    intent: Intent
    subtasks: list[SubTask] = Field(default_factory=list)
    # Set only for CHITCHAT / CLARIFICATION_NEEDED / OUT_OF_SCOPE — the
    # planner can answer directly without any retrieval or synthesis pass.
    direct_response: str | None = None