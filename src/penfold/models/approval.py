"""Modelo de la decisión humana de aprobación (solo declaración de clases)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApprovalDecision(BaseModel):
    """Respuesta de la puerta de aprobación humana."""

    decision: str
    data: Any = None
    note: str | None = None
