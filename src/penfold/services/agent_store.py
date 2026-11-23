"""Persistencia de definiciones de agentes en YAML."""

from __future__ import annotations

import yaml
from pydantic import ValidationError

from penfold.config.paths import ProjectPaths
from penfold.errors import NotFoundError
from penfold.errors import ValidationError as PenfoldValidationError
from penfold.models.agent import AgentDefinition


class AgentStore:
    def __init__(self, paths: ProjectPaths):
        self.paths = paths

    def list(self) -> list[AgentDefinition]:
        self.paths.agents_dir.mkdir(parents=True, exist_ok=True)
        agents: list[AgentDefinition] = []
        for path in sorted(self.paths.agents_dir.glob("*.yaml")):
            try:
                agents.append(self._parse(path.read_text(encoding="utf-8")))
            except (PenfoldValidationError, OSError):
                # Un archivo roto no debe impedir listar los demás.
                continue
        return agents

    def get(self, agent_id: str) -> AgentDefinition:
        path = self.paths.agent_path(agent_id)
        if not path.is_file():
            raise NotFoundError(f"Agente {agent_id!r} no encontrado en {path}")
        return self._parse(path.read_text(encoding="utf-8"))

    def exists(self, agent_id: str) -> bool:
        return self.paths.agent_path(agent_id).is_file()

    def save(self, agent: AgentDefinition) -> None:
        self.paths.ensure_layout()
        path = self.paths.agent_path(agent.id)
        data = agent.model_dump(mode="json", exclude_none=True, by_alias=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def delete(self, agent_id: str) -> None:
        path = self.paths.agent_path(agent_id)
        if not path.is_file():
            raise NotFoundError(f"Agente {agent_id!r} no encontrado")
        path.unlink()

    @staticmethod
    def _parse(raw: str) -> AgentDefinition:
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise PenfoldValidationError(f"YAML de agente inválido: {exc}") from exc
        try:
            return AgentDefinition.model_validate(data)
        except ValidationError as exc:
            raise PenfoldValidationError(f"Definición de agente inválida: {exc}") from exc
