"""Definición de agentes, independiente de workflows y de runtimes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RuntimeType = Literal["mock", "command"]
PermissionMode = Literal["read_only", "workspace_write", "restricted"]


class RuntimeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: RuntimeType = "mock"
    provider: str | None = None
    model: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)


class Permissions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: PermissionMode = "workspace_write"
    read_paths: list[str] = Field(default_factory=lambda: ["."])
    write_paths: list[str] = Field(default_factory=list)
    allowed_commands: list[str] = Field(default_factory=list)


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: str = "string"
    required: bool = True


class AgentOutputs(BaseModel):
    # El formato público usa 'schema'; internamente se llama json_schema para
    # no sombrear el método heredado de BaseModel.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    format: Literal["json", "text"] = "json"
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")


class MockBehavior(BaseModel):
    """Salida determinista usada únicamente por MockRuntime."""

    model_config = ConfigDict(extra="forbid")

    output: dict[str, Any] | None = None
    delay_seconds: float = 0.0


class AgentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    id: str
    name: str
    description: str = ""
    role: str = ""
    instructions: str = ""
    runtime: RuntimeSpec = Field(default_factory=RuntimeSpec)
    tools: list[str] = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)
    inputs: list[AgentInput] = Field(default_factory=list)
    outputs: AgentOutputs = Field(default_factory=AgentOutputs)
    timeout: int = 300
    retries: int = 1
    mock: MockBehavior = Field(default_factory=MockBehavior)

    @field_validator("schema_version")
    @classmethod
    def check_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"schema_version {value} no soportada")
        return value

    @field_validator("id")
    @classmethod
    def check_id(cls, value: str) -> str:
        if not value or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in value):
            raise ValueError("id debe usar letras minúsculas, números, - o _")
        return value

    @field_validator("timeout", "retries")
    @classmethod
    def non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("timeout y retries deben ser >= 0")
        return value
