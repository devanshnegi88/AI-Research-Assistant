"""
Tests for PlannerAgent — exercises the actual compiled LangGraph
StateGraph end to end, with a fake LLMClient standing in for Gemini.

These are unit tests against the agent directly (not through `/chat`) so
each routing branch and fallback path can be verified precisely against
crafted LLM outputs, including malformed ones.
"""

from __future__ import annotations

import json

import pytest

from app.agents.planner_agent import PlannerAgent
from app.schemas.agent import Intent

pytestmark = pytest.mark.asyncio


class _ScriptedLLMClient:
    """Returns each entry in `responses` in order, one per `generate()`
    call — lets a test dictate exactly what each graph node "sees" from
    the LLM without needing a real model."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def generate(
        self, system_prompt, user_prompt, json_mode: bool = False, temperature=None
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "json_mode": json_mode,
                "temperature": temperature,
            }
        )
        return self._responses.pop(0)


async def test_document_question_single_subtask_routes_to_decompose():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "document_question"}),
            json.dumps({"subtasks": [{"query": "What was Q3 revenue?"}]}),
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("What was Q3 revenue?")

    assert plan.intent == Intent.DOCUMENT_QUESTION
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].query == "What was Q3 revenue?"
    assert plan.direct_response is None
    assert len(llm.calls) == 2  # classify_intent, decompose_tasks — no direct-response call


async def test_document_question_multi_subtask_decomposition():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "document_question"}),
            json.dumps(
                {
                    "subtasks": [
                        {"query": "What did the Q1 report say about revenue?"},
                        {"query": "What did the Q2 report say about revenue?"},
                    ]
                }
            ),
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("Compare Q1 and Q2 revenue")

    assert plan.intent == Intent.DOCUMENT_QUESTION
    assert len(plan.subtasks) == 2
    assert plan.subtasks[0].query == "What did the Q1 report say about revenue?"
    assert plan.subtasks[1].query == "What did the Q2 report say about revenue?"


async def test_chitchat_routes_to_direct_response_and_skips_decomposition():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "chitchat"}),
            "Hi! I can help you find things in your documents.",
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("hello there")

    assert plan.intent == Intent.CHITCHAT
    assert plan.subtasks == []
    assert plan.direct_response == "Hi! I can help you find things in your documents."
    assert len(llm.calls) == 2  # classify_intent, generate_direct_response


async def test_clarification_needed_routes_to_direct_response():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "clarification_needed"}),
            "Could you clarify which document you mean?",
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("tell me about it")

    assert plan.intent == Intent.CLARIFICATION_NEEDED
    assert plan.direct_response == "Could you clarify which document you mean?"


async def test_out_of_scope_routes_to_direct_response():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "out_of_scope"}),
            "I can't book flights, but I can help you search your documents.",
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("book me a flight to Tokyo")

    assert plan.intent == Intent.OUT_OF_SCOPE


async def test_malformed_intent_json_falls_back_to_document_question():
    llm = _ScriptedLLMClient(
        [
            "not valid json at all",
            json.dumps({"subtasks": [{"query": "some question"}]}),
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("some question")

    # classify_intent's fallback defaults to DOCUMENT_QUESTION, which then
    # correctly routes to decompose_tasks next — the failure is contained
    # to one node, not the whole turn.
    assert plan.intent == Intent.DOCUMENT_QUESTION
    assert len(plan.subtasks) == 1


async def test_malformed_decomposition_json_falls_back_to_single_subtask():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "document_question"}),
            "{not valid json",
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("what does the report say?")

    assert plan.intent == Intent.DOCUMENT_QUESTION
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].query == "what does the report say?"


async def test_decomposition_respects_max_subtasks_cap():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "document_question"}),
            json.dumps({"subtasks": [{"query": f"subquestion {i}"} for i in range(10)]}),
        ]
    )
    agent = PlannerAgent(llm)

    plan = await agent.plan("a question with many angles")

    from app.core.config import settings

    assert len(plan.subtasks) == settings.PLANNER_MAX_SUBTASKS


async def test_history_is_included_in_classification_prompt():
    llm = _ScriptedLLMClient(
        [
            json.dumps({"intent": "document_question"}),
            json.dumps({"subtasks": [{"query": "What about the second one?"}]}),
        ]
    )
    agent = PlannerAgent(llm)

    from app.models.conversation import Message
    from app.models.enums import MessageRole

    history_message = Message(
        conversation_id=None,
        turn_index=0,
        role=MessageRole.USER,
        content="Tell me about the Q1 and Q2 reports",
    )

    await agent.plan(
        "What about the second one?",
        history_summary=None,
        history_messages=[history_message],
    )

    classify_call = llm.calls[0]
    assert "Q1 and Q2 reports" in classify_call["user_prompt"]