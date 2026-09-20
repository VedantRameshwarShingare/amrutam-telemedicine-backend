from __future__ import annotations


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str = "Application error") -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)
        self.message = message


class AuthorizationError(AppException):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message)
        self.message = message


class ResourceNotFoundError(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message)
        self.message = message


class ValidationError(AppException):
    def __init__(self, message: str = "Validation failed") -> None:
        super().__init__(message)
        self.message = message


class ConflictError(AppException):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message)
        self.message = message


class SlotAlreadyBookedError(ConflictError):
    pass


class IdempotencyConflictError(ConflictError):
    pass


class RateLimitExceededError(AppException):
    def __init__(self, message: str = "Too many requests") -> None:
        super().__init__(message)
        self.message = message


class InternalServerError(AppException):
    def __init__(self, message: str = "Internal server error") -> None:
        super().__init__(message)
        self.message = message
