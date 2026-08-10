"""
RAG service — retrieves relevant chunks, builds a citation-grounded prompt,
and generates an answer via the configured LLM.

Chunks are numbered [1], [2], ... in the prompt and the model is instructed
to cite them inline; those same numbers map back to `Citation` objects in
the response so the client can render clickable sources.
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.schemas.chat import Citation
from app.schemas.search import SearchFilters
from app.services.rag.llm_client import LLMClient
from app.services.search.search_service import SearchService

_SYSTEM_PROMPT = (
    "You are a research assistant answering questions using only the "
    "provided source excerpts. Rules:\n"
    "1. Base your answer strictly on the excerpts below — do not use "
    "outside knowledge.\n"
    "2. Cite sources inline using the bracketed number, e.g. [1], [2], "
    "immediately after the claim it supports.\n"
    "3. If the excerpts don't contain enough information to answer, say "
    "so plainly instead of guessing.\n"
    "4. Be concise and directly answer the question."
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
    ) -> tuple[str, list[Citation]]:
        top_k = max_context_chunks or settings.RAG_MAX_CONTEXT_CHUNKS

        results = await self.search_service.search(query, owner_id, top_k, filters)
        if not results:
            return (
                "I couldn't find any relevant documents to answer that question.",
                [],
            )

        user_prompt = self._build_prompt(query, results)
        answer_text = await self.llm_client.generate(_SYSTEM_PROMPT, user_prompt)

        citations = [
            Citation(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                document_filename=r.document_filename,
                chunk_index=r.chunk_index,
                excerpt=r.content[:_EXCERPT_CHAR_LIMIT],
            )
            for r in results
        ]

        return answer_text, citations

    def _build_prompt(self, query: str, results: list) -> str:
        excerpt_blocks = []
        for i, r in enumerate(results, start=1):
            excerpt = r.content[:_EXCERPT_CHAR_LIMIT]
            excerpt_blocks.append(
                f"[{i}] Source: {r.document_filename} (chunk {r.chunk_index})\n{excerpt}"
            )

        excerpts_text = "\n\n".join(excerpt_blocks)
        return f"Question: {query}\n\nSource excerpts:\n\n{excerpts_text}"