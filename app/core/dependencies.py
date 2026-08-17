"""
Shared FastAPI dependencies: DB/Redis-backed repository and service
providers, current-user extraction from JWT, and role-based access guards.
"""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.planner_agent import PlannerAgent
from app.core.config import settings
from app.core.exceptions import ForbiddenException, InvalidTokenException
from app.core.security import decode_token
from app.db.redis import get_redis
from app.db.session import get_db
from app.models.enums import RoleEnum
from app.models.user import User
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.chat.chat_service import ChatService
from app.services.chat.memory_manager import MemoryManager
from app.services.conversation.conversation_service import ConversationService
from app.services.document.document_service import DocumentService
from app.services.embedding.embedding_service import EmbeddingService, get_embedding_service
from app.services.rag.llm_client import LLMClient, get_llm_client
from app.services.rag.rag_service import RAGService
from app.services.search.retriever import HybridRetriever
from app.services.search.search_service import SearchService
from app.services.user_service import UserService
from app.storage.base import StorageBackend
from app.storage.local_storage import get_storage_backend
from app.vectorstore.base import VectorStore
from app.vectorstore.qdrant_store import get_vector_store

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


# --- Repositories ---

def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_document_repository(db: AsyncSession = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(db)


def get_storage() -> StorageBackend:
    return get_storage_backend()


def get_chunk_repository(db: AsyncSession = Depends(get_db)) -> ChunkRepository:
    return ChunkRepository(db)


def get_conversation_repository(
    db: AsyncSession = Depends(get_db),
) -> ConversationRepository:
    return ConversationRepository(db)


def get_message_repository(db: AsyncSession = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)


def get_vector_store_dep() -> VectorStore:
    return get_vector_store()


def get_embedding_service_dep() -> EmbeddingService:
    return get_embedding_service()


def get_llm_client_dep() -> LLMClient:
    return get_llm_client()


# --- Services ---

def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
    redis: Redis = Depends(get_redis),
) -> AuthService:
    return AuthService(user_repository, redis)


def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repository)


def get_document_service(
    document_repository: DocumentRepository = Depends(get_document_repository),
    storage: StorageBackend = Depends(get_storage),
    vector_store: VectorStore = Depends(get_vector_store_dep),
) -> DocumentService:
    return DocumentService(document_repository, storage, vector_store)


def get_hybrid_retriever(
    vector_store: VectorStore = Depends(get_vector_store_dep),
    embedding_service: EmbeddingService = Depends(get_embedding_service_dep),
    chunk_repository: ChunkRepository = Depends(get_chunk_repository),
) -> HybridRetriever:
    return HybridRetriever(vector_store, embedding_service, chunk_repository)


def get_search_service(
    retriever: HybridRetriever = Depends(get_hybrid_retriever),
    chunk_repository: ChunkRepository = Depends(get_chunk_repository),
    document_repository: DocumentRepository = Depends(get_document_repository),
) -> SearchService:
    return SearchService(retriever, chunk_repository, document_repository)


def get_rag_service(
    search_service: SearchService = Depends(get_search_service),
    llm_client: LLMClient = Depends(get_llm_client_dep),
) -> RAGService:
    return RAGService(search_service, llm_client)


def get_conversation_service(
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    message_repository: MessageRepository = Depends(get_message_repository),
) -> ConversationService:
    return ConversationService(conversation_repository, message_repository)


def get_memory_manager(
    llm_client: LLMClient = Depends(get_llm_client_dep),
) -> MemoryManager:
    return MemoryManager(llm_client)


def get_planner_agent(
    llm_client: LLMClient = Depends(get_llm_client_dep),
) -> PlannerAgent:
    return PlannerAgent(llm_client)


def get_chat_service(
    conversation_service: ConversationService = Depends(get_conversation_service),
    conversation_repository: ConversationRepository = Depends(get_conversation_repository),
    message_repository: MessageRepository = Depends(get_message_repository),
    memory_manager: MemoryManager = Depends(get_memory_manager),
    rag_service: RAGService = Depends(get_rag_service),
    search_service: SearchService = Depends(get_search_service),
    planner_agent: PlannerAgent = Depends(get_planner_agent),
) -> ChatService:
    return ChatService(
        conversation_service,
        conversation_repository,
        message_repository,
        memory_manager,
        rag_service,
        search_service,
        planner_agent,
    )


# --- Current user / RBAC ---

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_repository: UserRepository = Depends(get_user_repository),
) -> User:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise InvalidTokenException("Not an access token")

    user = await user_repository.get_by_id(uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise InvalidTokenException("User no longer active")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise ForbiddenException("Account is deactivated")
    return current_user


def require_role(*allowed_roles: RoleEnum):
    """Dependency factory — e.g. `Depends(require_role(RoleEnum.ADMIN))`."""

    async def _guard(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenException(
                f"Requires one of roles: {[r.value for r in allowed_roles]}"
            )
        return current_user

    return _guard


require_admin = require_role(RoleEnum.ADMIN)