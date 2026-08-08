"""
Celery application instance.

NOTE: Celery has been removed from the application (it depended on Redis as
its message broker). This module is kept only as a commented-out reference.
Document processing now runs synchronously inside the API request
(`app/services/document/document_service.py`).
"""

# from celery import Celery
#
# from app.core.config import settings
#
# celery_app = Celery(
#     "ai_research_assistant",
#     broker=settings.CELERY_BROKER_URL,
#     backend=settings.CELERY_RESULT_BACKEND,
#     include=["app.workers.tasks"],
# )
#
# celery_app.conf.update(
#     task_serializer="json",
#     result_serializer="json",
#     accept_content=["json"],
#     timezone="UTC",
#     enable_utc=True,
#     task_track_started=True,
#     task_acks_late=True,
#     worker_prefetch_multiplier=1,
#     task_time_limit=600,
#     task_soft_time_limit=540,
#     result_expires=86400,
# )
