"""Modelo de los resultados de validación estática (solo declaración de clases)."""

from __future__ import annotations

from pydantic import BaseModel


class ValidationIssue(BaseModel):
    """Hallazgo de la validación de un workflow."""

    path: str
    message: str
    severity: str = "error"
