"""Modelos del formato de workflows (definición ejecutable + posiciones visuales)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NodeType = Literal["input", "agent", "command", "condition", "approval", "output"]
Handle = Literal["default", "pass", "fail"]


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = 0
    y: float = 0


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: NodeType
    label: str | None = None
    agent: str | None = None
    description: str | None = None
    # Las posiciones son exclusivamente visuales; el motor las ignora.
    position: Position = Field(default_factory=Position)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def check_id(cls, value: str) -> str:
        if not value or any(
            ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for ch in value
        ):
            raise ValueError("node.id debe usar letras, números, - o _")
        return value


class EdgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: int | None = Field(default=None, ge=1, le=10)
    loop: bool = False


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    source_handle: Handle = "default"
    target_handle: str | None = None
    label: str | None = None
    config: EdgeConfig = Field(default_factory=EdgeConfig)

    @field_validator("id")
    @classmethod
    def check_id(cls, value: str) -> str:
        if not value or any(
            ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for ch in value
        ):
            raise ValueError("edge.id debe usar letras, números, - o _")
        return value


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str = "string"
    required: bool = True
    default: Any = None


class WorkflowMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""

    @field_validator("id")
    @classmethod
    def check_id(cls, value: str) -> str:
        if not value or any(
            ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in value.lower()
        ):
            raise ValueError("metadata.id debe usar letras minúsculas, números, - o _")
        return value


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    metadata: WorkflowMetadata
    inputs: list[WorkflowInput] = Field(default_factory=list)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def check_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"schema_version {value} no soportada (se espera 1)")
        return value

    @model_validator(mode="after")
    def check_unique_ids(self) -> WorkflowDefinition:
        for collection, label in (
            (self.nodes, "nodo"),
            (self.edges, "arista"),
            (self.inputs, "entrada"),
        ):
            seen: set[str] = set()
            for item in collection:
                if item.id in seen:
                    raise ValueError(f"ID duplicado de {label}: {item.id!r}")
                seen.add(item.id)
        return self
