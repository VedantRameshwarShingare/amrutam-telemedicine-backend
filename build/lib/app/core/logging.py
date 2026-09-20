from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from app.core.config import settings

SENSITIVE_LOG_KEYS = frozenset(
    {
        "authorization",
        "access_token",
        "refresh_token",
        "password",
        "password_hash",
        "mfa_secret",
        "clinical_notes",
        "payload",
        "email",
        "phone",
        "amount",
        "provider_payment_id",
    }
)


def redact_sensitive(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in SENSITIVE_LOG_KEYS:
        event_dict.pop(key, None)
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logger = logging.getLogger()
    logger.setLevel(settings.log_level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]


configure_logging()
logger = structlog.get_logger("amrutam.telemedicine")
