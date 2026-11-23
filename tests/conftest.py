"""Fixtures compartidas: proyecto temporal con agentes y workflows de ejemplo."""

from __future__ import annotations

from pathlib import Path

import pytest

from penfold.config.paths import ProjectPaths
from penfold.services.agent_store import AgentStore
from penfold.services.agent_templates import install_default_agents
from penfold.services.events import EventBus
from penfold.services.manager import RunManager
from penfold.services.repository import RunRepository
from penfold.services.workflow_store import WorkflowStore
from penfold.services.workflow_templates import install_default_workflows


@pytest.fixture
def project(tmp_path: Path) -> ProjectPaths:
    paths = ProjectPaths(tmp_path)
    paths.init(name="test-project")
    install_default_agents(paths)
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
