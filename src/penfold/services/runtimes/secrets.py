"""Redacción de secretos en logs y salidas."""

from __future__ import annotations

import os
import re

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{12,}", re.IGNORECASE),
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),
]
_SECRET_HINTS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH")


def redact(text: str) -> str:
    """Sustituye patrones de credenciales y valores de variables de entorno sensibles."""
    if not text:
        return text
    for pattern in _PATTERNS:
        text = pattern.sub("***REDACTED***", text)
    for name, value in os.environ.items():
        if len(value) < 4 or not any(hint in name.upper() for hint in _SECRET_HINTS):
            continue
        text = text.replace(value, "***REDACTED***")
    return text
