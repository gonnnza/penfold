"""Modelos de configuración del proyecto."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    auto_open_browser: bool = True

    @field_validator("host")
    @classmethod
    def only_loopback_by_default(cls, value: str) -> str:
        # El servidor escucha en localhost salvo configuración explícita.
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "server.host debe ser una dirección de loopback (127.0.0.1, localhost, ::1). "
                "Exponer el servidor requiere una decisión explícita y controles de seguridad."
            )
        return value


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrency: int = Field(default=4, ge=1, le=32)
    default_timeout_seconds: int = Field(default=300, ge=1)
    max_retries: int = Field(default=2, ge=0, le=10)
    max_iterations: int = Field(default=3, ge=1, le=10)
    max_output_chars: int = Field(default=50000, ge=1000)


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_permission_mode: str = "workspace_write"
    audit_sensitive_actions: bool = True

    @field_validator("default_permission_mode")
    @classmethod
    def valid_mode(cls, value: str) -> str:
        if value not in {"read_only", "workspace_write", "restricted"}:
            raise ValueError("modo de permisos inválido")
        return value


class DefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime: str = "mock"


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    project: dict[str, str] = Field(
        default_factory=lambda: {"name": "penfold-project", "description": ""}
    )
    server: ServerConfig = Field(default_factory=ServerConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    @field_validator("schema_version")
    @classmethod
    def version_supported(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"schema_version {value} no soportada (se espera 1)")
        return value
