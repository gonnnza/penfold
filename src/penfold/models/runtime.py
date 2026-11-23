"""Modelos de datos del contrato de runtime (solo declaración de clases)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from penfold.models.agent import AgentDefinition


class RuntimeContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    node_id: str
    agent: AgentDefinition | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    workspace: Path
    timeout: int = 300
    options: dict[str, Any] = Field(default_factory=dict)
    attempt: int = 1
    cancel_event: asyncio.Event | None = None


class RuntimeResult(BaseModel):
    output: dict[str, Any]
    logs: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
