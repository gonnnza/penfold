"""Fixtures compartidas: proyecto temporal con agentes y workflows de ejemplo."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from penfold.config.paths import ProjectPaths
from penfold.models.agent import AgentDefinition
from penfold.services.agent_store import AgentStore
from penfold.services.events import EventBus
from penfold.services.manager import RunManager
from penfold.services.repository import RunRepository
from penfold.services.workflow_store import WorkflowStore
from penfold.services.workflow_templates import install_default_workflows


def _install_test_agents(paths: ProjectPaths) -> None:
    """Agentes mínimos para los tests de nodos `agent`; no son plantillas de producto."""
    specs = [
        {
            "id": "product-analyst",
            "name": "Product Analyst",
            "role": "analyst",
            "runtime": {"type": "mock"},
            "permissions": {"mode": "read_only", "read_paths": ["."]},
            "inputs": [{"name": "feature_description", "type": "string"}],
            "outputs": {
                "format": "json",
                "schema": {
                    "type": "object",
                    "required": ["requirements", "acceptance_criteria"],
                    "properties": {
                        "requirements": {"type": "array", "items": {"type": "string"}},
                        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "retries": 1,
            "mock": {
                "output": {
                    "task": "demo",
                    "requirements": ["La funcionalidad solicitada está implementada"],
                    "acceptance_criteria": ["Los tests pasan"],
                    "assumptions": [],
                    "open_questions": [],
                }
            },
        },
        {
            "id": "architect",
            "name": "Architect Agent",
            "role": "architect",
            "runtime": {"type": "mock"},
            "mock": {"output": {"plan": ["Revisar el código existente"]}},
        },
    ]
    for spec in specs:
        agent = AgentDefinition.model_validate(spec)
        path = paths.agent_path(agent.id)
        path.write_text(
            yaml.safe_dump(agent.model_dump(mode="json", exclude_none=True), sort_keys=False),
            encoding="utf-8",
        )


@pytest.fixture
def project(tmp_path: Path) -> ProjectPaths:
    paths = ProjectPaths(tmp_path)
    paths.init(name="test-project")
    _install_test_agents(paths)
    install_default_workflows(paths)
    return paths


@pytest.fixture
def components(project: ProjectPaths):
    config = project.load_config()
    agents = AgentStore(project)
    workflows = WorkflowStore(project)
    repository = RunRepository(project.db_path)
    events = EventBus()
    manager = RunManager(project, config, workflows, agents, repository, events)
    return project, config, agents, workflows, repository, events, manager


@pytest.fixture
def failing_command_script(project: ProjectPaths) -> str:
    """Script real que falla una vez y luego pasa; sin shell ni mocks del motor."""
    script = project.root / "fake_tests.py"
    script.write_text(
        "import pathlib\n"
        "import sys\n"
        "counter = pathlib.Path(sys.argv[1])\n"
        "n = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(n + 1))\n"
        "print(f'intento {n + 1}')\n"
        "sys.exit(1 if n == 0 else 0)\n",
        encoding="utf-8",
    )
    return "python fake_tests.py .orchestrator/state/test-counter"
