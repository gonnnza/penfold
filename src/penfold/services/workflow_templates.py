"""Workflows de ejemplo instalados por ``penfold init``.

Son ejemplos ejecutables sin agentes: usan nodos `command` con comandos
locales inocuos. Para usar nodos `agent`, crea primero tus definiciones YAML en
`.orchestrator/agents/`.
"""

from __future__ import annotations

import yaml

from penfold.config.paths import ProjectPaths
from penfold.models.workflow import WorkflowDefinition


def simple_workflow() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "schema_version": 1,
            "metadata": {
                "id": "simple",
                "name": "Simple demo",
                "description": "Input -> agente (MockRuntime) -> comando -> Output",
            },
            "inputs": [
                {
                    "id": "feature_description",
                    "type": "string",
                    "required": True,
                    "default": "Añadir autenticación JWT",
                }
            ],
            "nodes": [
                {
                    "id": "start",
                    "type": "input",
                    "label": "User Request",
                    "description": "Petición inicial del usuario",
                    "position": {"x": 0, "y": 160},
                },
                {
                    "id": "analyst",
                    "type": "command",
                    "label": "Analizar requisitos",
                    "position": {"x": 260, "y": 160},
                    "config": {
                        "command": "python -c \"print('requirements for JWT')\"",
                        "timeout": 60,
                    },
                },
                {
                    "id": "tests",
                    "type": "command",
                    "label": "Run Tests",
                    "description": "Comando de ejemplo: reemplázalo por tu suite de tests real",
                    "position": {"x": 540, "y": 160},
                    "config": {
                        "command": "python -c \"print('replace with your test suite')\"",
                        "timeout": 60,
                    },
                },
                {
                    "id": "output",
                    "type": "output",
                    "label": "Final Report",
                    "position": {"x": 820, "y": 160},
                    "config": {
                        "format": "json",
                        "inputs": {
                            "requirements": "$nodes.analyst.output.stdout",
                            "tests": "$nodes.tests.output",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "analyst"},
                {"id": "e2", "source": "analyst", "target": "tests"},
                {"id": "e3", "source": "tests", "target": "output"},
            ],
        }
    )


def feature_development_workflow() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "schema_version": 1,
            "metadata": {
                "id": "feature-development",
                "name": "Feature Development",
                "description": "Analisis, desarrollo, tests y ciclo de correccion limitado",
            },
            "inputs": [
                {
                    "id": "feature_description",
                    "type": "string",
                    "required": True,
                    "default": "Implementar autenticacion JWT",
                }
            ],
            "nodes": [
                {
                    "id": "start",
                    "type": "input",
                    "label": "User Request",
                    "position": {"x": 0, "y": 220},
                },
                {
                    "id": "analyst",
                    "type": "command",
                    "label": "Analizar requisitos",
                    "position": {"x": 240, "y": 220},
                    "config": {"command": "python -c \"print('requirements')\""},
                },
                {
                    "id": "developer",
                    "type": "command",
                    "label": "Implementar cambio",
                    "position": {"x": 500, "y": 220},
                    "config": {"command": "python -c \"print('developer summary')\""},
                },
                {
                    "id": "tests",
                    "type": "command",
                    "label": "Test Runner",
                    "description": "Comando real de tests ejecutado en el workspace",
                    "position": {"x": 760, "y": 220},
                    "config": {
                        "command": "python -c \"print('replace with your test suite')\"",
                        "timeout": 120,
                    },
                },
                {
                    "id": "check",
                    "type": "condition",
                    "label": "Tests passed?",
                    "position": {"x": 1020, "y": 220},
                    "config": {
                        "inputs": {"passed": "$nodes.tests.output.passed"},
                        "expression": {"field": "passed", "op": "eq", "value": True},
                    },
                },
                {
                    "id": "output",
                    "type": "output",
                    "label": "Final Report",
                    "position": {"x": 1280, "y": 100},
                    "config": {
                        "format": "json",
                        "inputs": {
                            "summary": "$nodes.developer.output.stdout",
                            "tests": "$nodes.tests.output",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "analyst"},
                {"id": "e2", "source": "analyst", "target": "developer"},
                {"id": "e3", "source": "developer", "target": "tests"},
                {"id": "e4", "source": "tests", "target": "check"},
                {
                    "id": "e5",
                    "source": "check",
                    "target": "output",
                    "source_handle": "pass",
                    "label": "PASS",
                },
                {
                    "id": "e6",
                    "source": "check",
                    "target": "developer",
                    "source_handle": "fail",
                    "label": "FAIL",
                    "config": {"loop": True, "max_iterations": 3},
                },
            ],
        }
    )


def approval_workflow() -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "schema_version": 1,
            "metadata": {
                "id": "approval-demo",
                "name": "Human approval demo",
                "description": "Pausa la ejecución hasta que el usuario apruebe o rechace",
            },
            "inputs": [
                {
                    "id": "feature_description",
                    "type": "string",
                    "required": True,
                    "default": "Revisar propuesta",
                }
            ],
            "nodes": [
                {
                    "id": "start",
                    "type": "input",
                    "label": "User Request",
                    "position": {"x": 0, "y": 100},
                },
                {
                    "id": "analyst",
                    "type": "command",
                    "label": "Analizar propuesta",
                    "position": {"x": 240, "y": 100},
                    "config": {"command": "python -c \"print('requirements')\""},
                },
                {
                    "id": "approve",
                    "type": "approval",
                    "label": "Human Approval",
                    "position": {"x": 500, "y": 100},
                    "config": {
                        "title": "¿Aprobar el análisis?",
                        "message": "Revisa los requisitos propuestos.",
                        "inputs": {"requirements": "$nodes.analyst.output.stdout"},
                    },
                },
                {
                    "id": "output",
                    "type": "output",
                    "label": "Final Report",
                    "position": {"x": 760, "y": 100},
                    "config": {"format": "json", "inputs": {"result": "$nodes.approve.output"}},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "analyst"},
                {"id": "e2", "source": "analyst", "target": "approve"},
                {"id": "e3", "source": "approve", "target": "output"},
            ],
        }
    )


def default_workflows() -> list[WorkflowDefinition]:
    return [simple_workflow(), feature_development_workflow(), approval_workflow()]


def install_default_workflows(paths: ProjectPaths) -> int:
    paths.ensure_layout()
    created = 0
    for workflow in default_workflows():
        path = paths.workflow_path(workflow.metadata.id)
        if path.exists():
            continue
        data = workflow.model_dump(mode="json", exclude_none=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        created += 1
    return created
