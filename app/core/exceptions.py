"""
Custom exception hierarchy.

Services and repositories raise these instead of HTTPException directly —
keeps the domain/business layers framework-agnostic. Translation to HTTP
responses happens centrally in `app/middleware/exception_handlers.py`.
"""

from __future__ import annotations


class AppException(Exception):
    """Base class for all application-raised exceptions."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str | None = None, **extra: object) -> None:
        self.message = message or self.__class__.__doc__ or "An error occurred"
        self.extra = extra
        super().__init__(self.message)


# --- 400s ---

class BadRequestException(AppException):
    """The request could not be processed as given."""

    status_code = 400
    error_code = "bad_request"


class ValidationException(AppException):
    """Input failed domain-level validation."""

    status_code = 422
    error_code = "validation_error"


class UnauthorizedException(AppException):
    """Authentication is required or the provided credentials are invalid."""

    status_code = 401
    error_code = "unauthorized"


class InvalidCredentialsException(UnauthorizedException):
    """Email or password is incorrect."""

    error_code = "invalid_credentials"


class TokenExpiredException(UnauthorizedException):
    """The provided JWT has expired."""

    error_code = "token_expired"


class InvalidTokenException(UnauthorizedException):
    """The provided JWT is malformed, tampered with, or revoked."""

    error_code = "invalid_token"


class ForbiddenException(AppException):
    """The authenticated user lacks permission for this action."""

    status_code = 403
    error_code = "forbidden"


class NotFoundException(AppException):
    """The requested resource does not exist."""

    status_code = 404
    error_code = "not_found"


class ConflictException(AppException):
    """The request conflicts with the current state of the resource."""

    status_code = 409
    error_code = "conflict"


class UserAlreadyExistsException(ConflictException):
    """A user with this email already exists."""

    error_code = "user_already_exists"


# --- 500s ---

class DatabaseException(AppException):
    """An unexpected database error occurred."""

    status_code = 500
    error_code = "database_error"
