"""Utilidades puras compartidas por modelos y servicios."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> str:
    """Timestamp ISO 8601 en UTC con resolución de milisegundos."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")
