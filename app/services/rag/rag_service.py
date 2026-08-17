"""
RAG service — retrieves relevant chunks, builds a citation-grounded prompt,
and generates an answer via the configured LLM.

Chunks are numbered [1], [2], ... in the prompt and the model is instructed
to cite them inline; those same numbers map back to `Citation` objects in
the response so the client can render clickable sources.

Phase 4: also accepts optional conversation history (a rolling summary +
recent messages verbatim, assembled by `MemoryManager`) so multi-turn
conversations stay coherent — a follow-up question like "what about the
second one?" only makes sense with the prior turn in context.

Phase 5: `answer()` remains the single-query path (unchanged — most
questions are one subtask). `synthesize()` is new — it takes
already-retrieved, already-merged results from the planner's possibly
multiple subtasks and generates one coherent, citation-grounded answer to
the *original* user question, rather than doing its own retrieval.
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.models.conversation import Message
from app.models.enums import MessageRole
from app.schemas.chat import Citation
from app.schemas.search import SearchFilters, SearchResultItem
from app.services.rag.llm_client import LLMClient
from app.services.search.search_service import SearchService

_SYSTEM_PROMPT = (
    "You are a research assistant answering questions using the provided "
    "source excerpts and the ongoing conversation. Rules:\n"
    "1. Base factual claims strictly on the source excerpts — do not use "
    "outside knowledge for facts about the user's documents.\n"
    "2. Cite sources inline using the bracketed number, e.g. [1], [2], "
    "immediately after the claim it supports.\n"
    "3. Use the conversation history to resolve references like \"it\" or "
    "\"the second one\", and to keep continuity — but only cite sources "
    "for claims grounded in the excerpts below, not the history itself.\n"
    "4. If the excerpts don't contain enough information to answer, say "
    "so plainly instead of guessing.\n"
    "5. Be concise and directly answer the question."
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are a research assistant. The excerpts below were gathered from "
    "several separate searches to answer one user question with multiple "
    "parts (e.g. a comparison). Synthesize ONE coherent answer that "
    "addresses all parts of the question — do not just answer each part "
    "in isolation; connect them where relevant (e.g. explicitly compare "
    "or contrast). Rules:\n"
    "1. Base factual claims strictly on the source excerpts.\n"
    "2. Cite sources inline using the bracketed number, e.g. [1], [2].\n"
    "3. If some parts of the question have no supporting excerpts, say so "
    "for that part specifically rather than skipping it silently.\n"
    "4. Be concise."
)

_NO_CONTEXT_SYSTEM_PROMPT = (
    "You are a research assistant. No source excerpts were found for this "
    "message. Continue the conversation naturally using the history "
    "provided, but if the user is asking about their documents, say "
    "plainly that you couldn't find anything relevant rather than "
    "guessing."
)

_EXCERPT_CHAR_LIMIT = 1500


class RAGService:
    def __init__(self, search_service: SearchService, llm_client: LLMClient) -> None:
        self.search_service = search_service
        self.llm_client = llm_client

    async def answer(
        self,
        query: str,
        owner_id: uuid.UUID,
        filters: SearchFilters | None = None,
        max_context_chunks: int | None = None,
        history_messages: list[Message] | None = None,
        history_summary: str | None = None,
    ) -> tuple[str, list[Citation]]:
        top_k = max_context_chunks or settings.RAG_MAX_CONTEXT_CHUNKS

        results = await self.search_service.search(query, owner_id, top_k, filters)
        history_block = self._build_history_block(history_messages, history_summary)

        if not results:
            if not history_block:
                return (
                    "I couldn't find any relevant documents to answer that question.",
                    [],
                )
            # No relevant docs, but there's conversation context — let the
            # model respond conversationally rather than bailing outright.
            user_prompt = f"{history_block}Current message: {query}"
            answer_text = await self.llm_client.generate(
                _NO_CONTEXT_SYSTEM_PROMPT, user_prompt
            )
            return answer_text, []

        user_prompt = self._build_prompt(
            "Current question", query, results, history_block
        )
        answer_text = await self.llm_client.generate(_SYSTEM_PROMPT, user_prompt)

        return answer_text, self._to_citations(results)

    async def synthesize(
        self,
        original_query: str,
        results: list[SearchResultItem],
        history_messages: list[Message] | None = None,
        history_summary: str | None = None,
    ) -> tuple[str, list[Citation]]:
        """Generate from results the caller already retrieved (and merged
        across however many subtasks the planner decomposed the question
        into) — no retrieval happens here."""
        history_block = self._build_history_block(history_messages, history_summary)

        if not results:
            if not history_block:
                return (
                    "I couldn't find any relevant documents to answer that question.",
                    [],
                )
            user_prompt = f"{history_block}Current message: {original_query}"
            answer_text = await self.llm_client.generate(
                _NO_CONTEXT_SYSTEM_PROMPT, user_prompt
            )
            return answer_text, []

        user_prompt = self._build_prompt(
            "Original question", original_query, results, history_block
        )
        answer_text = await self.llm_client.generate(
            _SYNTHESIS_SYSTEM_PROMPT, user_prompt
        )

        return answer_text, self._to_citations(results)

    def _to_citations(self, results: list[SearchResultItem]) -> list[Citation]:
        return [
            Citation(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                document_filename=r.document_filename,
                chunk_index=r.chunk_index,
                excerpt=r.content[:_EXCERPT_CHAR_LIMIT],
            )
            for r in results
        ]

    def _build_history_block(
        self, history_messages: list[Message] | None, history_summary: str | None
    ) -> str:
        parts = []
        if history_summary:
            parts.append(f"Summary of earlier conversation:\n{history_summary}")
        if history_messages:
            transcript = "\n".join(
                f"{'User' if m.role == MessageRole.USER else 'Assistant'}: {m.content}"
                for m in history_messages
            )
            parts.append(f"Recent conversation:\n{transcript}")

        if not parts:
            return ""
        return "\n\n".join(parts) + "\n\n"

    def _build_prompt(
        self,
        question_label: str,
        query: str,
        results: list[SearchResultItem],
        history_block: str,
    ) -> str:
        excerpt_blocks = []
        for i, r in enumerate(results, start=1):
            excerpt = r.content[:_EXCERPT_CHAR_LIMIT]
            excerpt_blocks.append(
                f"[{i}] Source: {r.document_filename} (chunk {r.chunk_index})\n{excerpt}"
            )

        excerpts_text = "\n\n".join(excerpt_blocks)
        return (
            f"{history_block}{question_label}: {query}\n\n"
            f"Source excerpts:\n\n{excerpts_text}"
        )