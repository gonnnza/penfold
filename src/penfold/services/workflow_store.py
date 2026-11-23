"""Persistencia de workflows en YAML versionable."""

from __future__ import annotations

import yaml
from pydantic import ValidationError

from penfold.config.paths import ProjectPaths
from penfold.errors import NotFoundError
from penfold.errors import ValidationError as PenfoldValidationError
from penfold.models.workflow import WorkflowDefinition


class WorkflowStore:
    def __init__(self, paths: ProjectPaths):
        self.paths = paths

    def list(self) -> list[WorkflowDefinition]:
        self.paths.workflows_dir.mkdir(parents=True, exist_ok=True)
        workflows: list[WorkflowDefinition] = []
        for path in sorted(self.paths.workflows_dir.glob("*.yaml")):
            try:
                workflows.append(self._parse(path.read_text(encoding="utf-8")))
            except (PenfoldValidationError, OSError):
                continue
        return workflows

    def get(self, workflow_id: str) -> WorkflowDefinition:
        path = self.paths.workflow_path(workflow_id)
        if not path.is_file():
            raise NotFoundError(f"Workflow {workflow_id!r} no encontrado en {path}")
        definition = self._parse(path.read_text(encoding="utf-8"))
        if definition.metadata.id != workflow_id:
            raise PenfoldValidationError(
                f"El archivo {path.name} declara metadata.id={definition.metadata.id!r}"
            )
        return definition

    def exists(self, workflow_id: str) -> bool:
        return self.paths.workflow_path(workflow_id).is_file()

    def save(self, workflow: WorkflowDefinition) -> None:
        self.paths.ensure_layout()
        path = self.paths.workflow_path(workflow.metadata.id)
        data = workflow.model_dump(mode="json", exclude_none=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def delete(self, workflow_id: str) -> None:
        path = self.paths.workflow_path(workflow_id)
        if not path.is_file():
            raise NotFoundError(f"Workflow {workflow_id!r} no encontrado")
        path.unlink()

    @staticmethod
    def _parse(raw: str) -> WorkflowDefinition:
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise PenfoldValidationError(f"YAML de workflow inválido: {exc}") from exc
        try:
            return WorkflowDefinition.model_validate(data)
        except ValidationError as exc:
            raise PenfoldValidationError(f"Definición de workflow inválida: {exc}") from exc
