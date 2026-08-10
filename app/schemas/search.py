"""Hybrid search route — retrieval only, no generation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_active_user, get_search_service
from app.models.user import User
from app.schemas.search import SearchQuery, SearchResponse
from app.services.search.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search_documents(
    payload: SearchQuery,
    current_user: User = Depends(get_current_active_user),
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    results = await search_service.search(
        query=payload.query,
        owner_id=current_user.id,
        top_k=payload.top_k,
        filters=payload.filters,
    )
    return SearchResponse(
        query=payload.query, results=results, total_results=len(results)
    )