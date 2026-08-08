# TODO — Remove Redis (comment-out approach)

- [x] `app/core/config.py` — comment out Redis settings block + Celery URL validators
- [x] `app/db/redis.py` — comment out file contents (Redis client)
- [x] `app/services/auth_service.py` — comment out Redis usage; make refresh/logout stateless
- [x] `app/core/dependencies.py` — comment out Redis import & injection
- [x] `app/workers/tasks.py` — comment out Celery task (keep file)
- [x] `app/workers/celery_app.py` — comment out Celery broker/backend config
- [x] `app/services/document/document_service.py` — replace `process_document.delay()` with synchronous processing
- [x] `docker-compose.yml` — comment out redis service + worker
- [x] `requirements.txt` — comment out redis/celery
- [x] `.env` — comment out redis/celery config
- [x] `tests/test_documents.py` — remove Celery mock, update status assertions
- [ ] Verify app imports / run tests
