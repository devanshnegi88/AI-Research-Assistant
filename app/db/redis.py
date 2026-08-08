"""
Redis connection — used for JWT refresh-token/blacklist storage and
general caching. Single shared connection pool for the process lifetime.

NOTE: Redis has been removed from the application. This module is kept
only as a commented-out reference. No code imports it anymore.
"""

# import redis.asyncio as redis
#
# from app.core.config import settings
#
# redis_pool: redis.ConnectionPool = redis.ConnectionPool.from_url(
#     str(settings.REDIS_URL),
#     decode_responses=True,
# )
#
#
# def get_redis_client() -> redis.Redis:
#     """Return a Redis client bound to the shared connection pool."""
#     return redis.Redis(connection_pool=redis_pool)
#
#
# async def get_redis() -> AsyncGenerator[redis.Redis, None]:
#     """FastAPI dependency yielding a Redis client for the request."""
#     client = get_redis_client()
#     try:
#         yield client
#     finally:
#         await client.aclose()
