"""Error handling — standardized error categories, timeouts, and retry logic."""

import enum
import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("datapulse.errors")


class ErrorCategory(str, enum.Enum):
    """Standardized error categories for DataPulse operations."""

    # Data source errors
    SOURCE_NOT_FOUND = "source_not_found"
    SOURCE_NOT_READABLE = "source_not_readable"
    SOURCE_TIMEOUT = "source_timeout"

    # Schema errors
    SCHEMA_MISMATCH = "schema_mismatch"
    SCHEMA_MISSING_COLUMNS = "schema_missing_columns"
    SCHEMA_UNEXPECTED_COLUMNS = "schema_unexpected_columns"
    SCHEMA_TYPE_VIOLATION = "schema_type_violation"

    # Data quality errors
    ROW_COUNT_OUT_OF_RANGE = "row_count_out_of_range"
    DUPLICATE_KEYS = "duplicate_keys"
    FRESHNESS_EXCEEDED = "freshness_exceeded"

    # Infrastructure errors
    DATABASE_ERROR = "database_error"
    NETWORK_ERROR = "network_error"
    AUTHENTICATION_ERROR = "authentication_error"
    TIMEOUT = "timeout"

    # Concurrency errors
    DUPLICATE_RUN = "duplicate_run"
    CONCURRENT_LIMIT_EXCEEDED = "concurrent_limit_exceeded"

    # Unknown
    UNKNOWN = "unknown"


class DataPulseError(Exception):
    """Base exception for DataPulse operations."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        retryable: bool = False,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.details = details or {}


class SourceNotFoundError(DataPulseError):
    def __init__(self, source_uri: str, details: dict | None = None):
        super().__init__(
            message=f"Source not found: {source_uri}",
            category=ErrorCategory.SOURCE_NOT_FOUND,
            retryable=False,
            details={"source_uri": source_uri, **(details or {})},
        )


class SourceTimeoutError(DataPulseError):
    def __init__(self, source_uri: str, timeout_seconds: float):
        super().__init__(
            message=f"Source timed out after {timeout_seconds}s: {source_uri}",
            category=ErrorCategory.SOURCE_TIMEOUT,
            retryable=True,
            details={"source_uri": source_uri, "timeout_seconds": timeout_seconds},
        )


class DuplicateRunError(DataPulseError):
    def __init__(self, run_id: str, pipeline_name: str):
        super().__init__(
            message=f"Duplicate run '{run_id}' for pipeline '{pipeline_name}'",
            category=ErrorCategory.DUPLICATE_RUN,
            retryable=False,
            details={"run_id": run_id, "pipeline_name": pipeline_name},
        )


class ConcurrentLimitError(DataPulseError):
    def __init__(self, pipeline_name: str, current_count: int, max_concurrent: int):
        super().__init__(
            message=f"Concurrent run limit exceeded for '{pipeline_name}': {current_count}/{max_concurrent}",
            category=ErrorCategory.CONCURRENT_LIMIT_EXCEEDED,
            retryable=True,
            details={
                "pipeline_name": pipeline_name,
                "current_count": current_count,
                "max_concurrent": max_concurrent,
            },
        )


def with_timeout(timeout_seconds: float) -> Callable:
    """Decorator that adds timeout to a function call.

    Usage:
        @with_timeout(30.0)
        def my_function():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            import signal

            def timeout_handler(signum, frame):
                raise SourceTimeoutError("Operation timed out", timeout_seconds)

            # Only works on Unix (not Windows)
            try:
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
                try:
                    result = func(*args, **kwargs)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, old_handler)
            except AttributeError:
                # Windows — no SIGALRM, just run without timeout
                result = func(*args, **kwargs)

            return result

        return wrapper

    return decorator


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_categories: list[ErrorCategory] | None = None,
) -> Callable:
    """Decorator that adds retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        retryable_categories: Error categories to retry (None = retry all DataPulseErrors with retryable=True)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except DataPulseError as e:
                    last_error = e
                    should_retry = False

                    if retryable_categories is not None:
                        should_retry = e.category in retryable_categories
                    else:
                        should_retry = e.retryable

                    if not should_retry or attempt == max_attempts - 1:
                        raise

                    delay = min(base_delay * (2**attempt), max_delay)
                    logger.warning(
                        "retry_attempt",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "delay": delay,
                            "error": str(e),
                            "category": e.category.value,
                        },
                    )
                    time.sleep(delay)

            raise last_error  # Should not reach here

        return wrapper

    return decorator
