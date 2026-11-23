"""Modelo de datos del repositorio Git (solo declaración de clases)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class RepoInfo(BaseModel):
    """Estado puntual de un repositorio Git local."""

    model_config = ConfigDict(frozen=True)

    root: Path
    branch: str
    clean: bool
    changed_files: list[str]
