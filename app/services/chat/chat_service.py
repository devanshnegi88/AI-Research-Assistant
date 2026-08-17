"""
Chat service — the top-level orchestrator for a single `/chat` turn.

Flow: resolve/create conversation -> load history -> build memory context
(recent verbatim + rolling summary) -> resummarize if needed -> plan (the
LangGraph planner agent decides intent + retrieval strategy) -> route:
  - chitchat / clarification_needed / out_of_scope -> use the planner's
    direct_response as-is, no retrieval, no synthesis call.
  - document_question, single subtask -> RAGService.answer() (Phase 4
    path, unchanged).
  - document_question, multiple subtasks -> search per subtask, merge +
    dedupe the results, RAGService.synthesize() over the merged set.
-> persist both messages -> return response (including the plan, so the
API layer can surface what the agent decided).

This is the only place that touches ConversationService, PlannerAgent,
SearchService, and RAGService together — everything downstream of it
stays single-purpose.
"""

from __future__ import annotations

import uuid

from app.agents.planner_agent import PlannerAgent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.agent import ExecutionPlan, Intent
from app.schemas.chat import Citation
from app.schemas.search import SearchFilters, SearchResultItem
from app.services.chat.memory_manager import MemoryManager, estimate_tokens
from app.services.conversation.conversation_service import ConversationService
from app.services.rag.rag_service import RAGService
from app.services.search.search_service import SearchService

logger = get_logger(__name__)


class ChatService:
    def __init__(
        self,
        conversation_service: ConversationService,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
        memory_manager: MemoryManager,
        rag_service: RAGService,
        search_service: SearchService,
        planner_agent: PlannerAgent,
    ) -> None:
        self.conversation_service = conversation_service
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository
        self.memory_manager = memory_manager
        self.rag_service = rag_service
        self.search_service = search_service
        self.planner_agent = planner_agent

    async def send_message(
        self,
        owner_id: uuid.UUID,
        message: str,
        conversation_id: uuid.UUID | None,
        filters: SearchFilters | None = None,
        max_context_chunks: int | None = None,
    ) -> tuple[Conversation, Message, list[Citation], ExecutionPlan]:
        conversation = await self.conversation_service.get_or_create(
            owner_id, conversation_id
        )
        history = await self.message_repository.list_for_conversation(conversation.id)

        conversation = await self._maybe_resummarize(conversation, history)
        context = await self.memory_manager.build_context(conversation, history)

        plan = await self.planner_agent.plan(
            message=message,
            history_summary=context.summary,
            history_messages=context.recent_messages,
        )
        logger.info(
            "planner_decision",
            extra={
                "conversation_id": str(conversation.id),
                "intent": plan.intent.value,
                "subtask_count": len(plan.subtasks),
            },
        )

        answer_text, citations = await self._execute_plan(
            plan=plan,
            message=message,
            owner_id=owner_id,
            filters=filters,
            max_context_chunks=max_context_chunks,
            history_messages=context.recent_messages,
            history_summary=context.summary,
        )

        user_message, assistant_message = await self._persist_turn(
            conversation, message, answer_text, citations
        )

        logger.info(
            "chat_turn_completed",
            extra={
                "conversation_id": str(conversation.id),
                "turn_index": assistant_message.turn_index,
            },
        )
        return conversation, assistant_message, citations, plan

    async def _execute_plan(
        self,
        plan: ExecutionPlan,
        message: str,
        owner_id: uuid.UUID,
        filters: SearchFilters | None,
        max_context_chunks: int | None,
        history_messages: list[Message],
        history_summary: str | None,
    ) -> tuple[str, list[Citation]]:
        if plan.intent != Intent.DOCUMENT_QUESTION:
            # Planner already generated the reply — chitchat/clarification/
            # out-of-scope never touch retrieval or a second LLM call.
            return plan.direct_response or "", []

        if len(plan.subtasks) <= 1:
            query = plan.subtasks[0].query if plan.subtasks else message
            subtask_filters = plan.subtasks[0].filters if plan.subtasks else None
            return await self.rag_service.answer(
                query=query,
                owner_id=owner_id,
                filters=subtask_filters or filters,
                max_context_chunks=max_context_chunks,
                history_messages=history_messages,
                history_summary=history_summary,
            )

        merged_results = await self._retrieve_for_subtasks(
            plan, owner_id, filters, max_context_chunks
        )
        return await self.rag_service.synthesize(
            original_query=message,
            results=merged_results,
            history_messages=history_messages,
            history_summary=history_summary,
        )

    async def _retrieve_for_subtasks(
        self,
        plan: ExecutionPlan,
        owner_id: uuid.UUID,
        filters: SearchFilters | None,
        max_context_chunks: int | None,
    ) -> list[SearchResultItem]:
        per_subtask_top_k = max_context_chunks or settings.RAG_MAX_CONTEXT_CHUNKS

        by_chunk_id: dict[uuid.UUID, SearchResultItem] = {}
        for subtask in plan.subtasks:
            results = await self.search_service.search(
                query=subtask.query,
                owner_id=owner_id,
                top_k=per_subtask_top_k,
                filters=subtask.filters or filters,
            )
            for r in results:
                # A chunk relevant to multiple subtasks keeps its best
                # (highest-scoring) appearance rather than being duplicated.
                existing = by_chunk_id.get(r.chunk_id)
                if existing is None or r.score > existing.score:
                    by_chunk_id[r.chunk_id] = r

        merged = sorted(by_chunk_id.values(), key=lambda r: r.score, reverse=True)
        overall_cap = max_context_chunks or settings.RAG_MAX_CONTEXT_CHUNKS
        return merged[:overall_cap]

    async def _maybe_resummarize(
        self, conversation: Conversation, history: list[Message]
    ) -> Conversation:
        if not history or not self.memory_manager.needs_resummarization(
            conversation, history
        ):
            return conversation

        new_summary, new_cutoff = await self.memory_manager.resummarize(
            conversation, history
        )
        conversation.summary = new_summary
        conversation.summarized_up_to_index = new_cutoff
        await self.conversation_repository.session.flush()
        logger.info(
            "conversation_resummarized",
            extra={
                "conversation_id": str(conversation.id),
                "summarized_up_to_index": new_cutoff,
            },
        )
        return conversation

    async def _persist_turn(
        self,
        conversation: Conversation,
        user_text: str,
        answer_text: str,
        citations: list[Citation],
    ) -> tuple[Message, Message]:
        next_index = await self.message_repository.get_next_turn_index(conversation.id)

        user_message = Message(
            conversation_id=conversation.id,
            turn_index=next_index,
            role=MessageRole.USER,
            content=user_text,
            token_estimate=estimate_tokens(user_text),
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            turn_index=next_index + 1,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            citations=[c.model_dump(mode="json") for c in citations] or None,
            token_estimate=estimate_tokens(answer_text),
        )

        self.message_repository.session.add_all([user_message, assistant_message])
        conversation.message_count += 2

        # First turn — derive a short title from the opening message so
        # conversations aren't all just "New conversation" in a list view.
        if conversation.message_count == 2:
            conversation.title = user_text[:80]

        await self.message_repository.session.flush()
        await self.message_repository.session.refresh(user_message)
        await self.message_repository.session.refresh(assistant_message)

        return user_message, assistant_message