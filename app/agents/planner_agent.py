"""
Planner agent — LangGraph StateGraph wiring.

Graph shape:

    START -> classify_intent --+-> decompose_tasks -----> finalize -> END
                                |
                                +-> generate_direct_response -> finalize

classify_intent always runs first. route_after_intent (a conditional
edge) then sends DOCUMENT_QUESTION down the retrieval-planning branch and
everything else (chitchat / clarification_needed / out_of_scope) down the
direct-response branch. Both branches converge on finalize, which just
assembles the ExecutionPlan from whatever the branch populated.

PlannerAgent.plan() is the only method the rest of the app calls — nothing
outside this module needs to know it's a graph rather than a plain
function, keeping LangGraph itself an implementation detail behind one
class, consistent with how LLMClient/VectorStore are used elsewhere.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import PlannerNodes, route_after_intent
from app.agents.state import PlannerState
from app.models.conversation import Message
from app.schemas.agent import ExecutionPlan
from app.services.rag.llm_client import LLMClient


class PlannerAgent:
    def __init__(self, llm_client: LLMClient) -> None:
        self._nodes = PlannerNodes(llm_client)
        self._graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(PlannerState)

        builder.add_node("classify_intent", self._nodes.classify_intent)
        builder.add_node("decompose_tasks", self._nodes.decompose_tasks)
        builder.add_node("generate_direct_response", self._nodes.generate_direct_response)
        builder.add_node("finalize", self._nodes.finalize)

        builder.add_edge(START, "classify_intent")
        builder.add_conditional_edges(
            "classify_intent",
            route_after_intent,
            {
                "decompose_tasks": "decompose_tasks",
                "generate_direct_response": "generate_direct_response",
            },
        )
        builder.add_edge("decompose_tasks", "finalize")
        builder.add_edge("generate_direct_response", "finalize")
        builder.add_edge("finalize", END)

        return builder.compile()

    async def plan(
        self,
        message: str,
        history_summary: str | None = None,
        history_messages: list[Message] | None = None,
    ) -> ExecutionPlan:
        initial_state: PlannerState = {
            "message": message,
            "history_summary": history_summary,
            "history_messages": history_messages or [],
        }
        final_state = await self._graph.ainvoke(initial_state)
        return final_state["plan"]