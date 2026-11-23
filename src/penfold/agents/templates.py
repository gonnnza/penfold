"""Agentes iniciales creados por ``penfold init``.

Son ejemplos configurables, no roles codificados en el motor. Cualquier agente
puede reemplazarse, editarse o eliminarse sin tocar el motor de ejecución.
"""

from __future__ import annotations

import yaml

from penfold.agents.models import AgentDefinition
from penfold.config.paths import ProjectPaths


def _agent(
    agent_id: str,
    name: str,
    role: str,
    instructions: str,
    output_schema: dict,
    mock_output: dict,
    *,
    mode: str = "read_only",
    runtime: str = "mock",
    command: str | None = None,
    inputs: list[tuple[str, str]] | None = None,
    tools: list[str] | None = None,
    write_paths: list[str] | None = None,
) -> AgentDefinition:
    return AgentDefinition(
        id=agent_id,
        name=name,
        role=role,
        description=f"Agente {role} de ejemplo. Edita .orchestrator/agents/{agent_id}.yaml.",
        instructions=instructions,
        runtime={"type": runtime, "command": command} if command else {"type": runtime},
        tools=tools or [],
        permissions={
            "mode": mode,
            "read_paths": ["."],
            "write_paths": write_paths or [],
            "allowed_commands": [],
        },
        inputs=[{"name": name_, "type": type_} for name_, type_ in (inputs or [])],
        outputs={"format": "json", "schema": output_schema},
        timeout=300,
        retries=1,
        mock={"output": mock_output},
    )


STRING_ARRAY = {"type": "array", "items": {"type": "string"}}


def default_agents() -> list[AgentDefinition]:
    return [
        _agent(
            "product-analyst",
            "Product Analyst",
            "analyst",
            "Comprende la petición, extrae requisitos, detecta ambigüedades y propone "
            "criterios de aceptación verificables. No propone una solución técnica.",
            {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "requirements": STRING_ARRAY,
                    "acceptance_criteria": STRING_ARRAY,
                    "assumptions": STRING_ARRAY,
                    "open_questions": STRING_ARRAY,
                },
                "required": ["task", "requirements", "acceptance_criteria"],
            },
            {
                "task": "Simulación: analizar la funcionalidad solicitada",
                "requirements": ["La funcionalidad solicitada debe estar implementada"],
                "acceptance_criteria": ["Los tests del proyecto pasan correctamente"],
                "assumptions": ["El repositorio contiene una suite de tests"],
                "open_questions": [],
            },
            inputs=[("feature_description", "string")],
        ),
        _agent(
            "prompt-engineer",
            "Prompt Engineer",
            "prompt_engineer",
            "Convierte requisitos estructurados en instrucciones técnicas claras, con "
            "contexto mínimo y restricciones explícitas.",
            {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "context": STRING_ARRAY,
                    "constraints": STRING_ARRAY,
                    "expected_output": {"type": "string"},
                },
                "required": ["prompt", "constraints"],
            },
            {
                "prompt": "Simulación: implementa la funcionalidad siguiendo los requisitos.",
                "context": ["requirements from product-analyst"],
                "constraints": ["No modificar archivos fuera del workspace"],
                "expected_output": "Cambios en el repositorio y resumen de los mismos",
            },
            inputs=[("requirements", "object")],
        ),
        _agent(
            "architect",
            "Architect Agent",
            "architect",
            "Analiza la arquitectura existente, identifica componentes afectados, "
            "propone un plan mínimo y detecta riesgos.",
            {
                "type": "object",
                "properties": {
                    "plan": STRING_ARRAY,
                    "decisions": STRING_ARRAY,
                    "affected_files": STRING_ARRAY,
                    "risks": STRING_ARRAY,
                },
                "required": ["plan", "affected_files"],
            },
            {
                "plan": ["Simulación: revisar el código existente"],
                "decisions": [],
                "affected_files": [],
                "risks": [],
            },
            inputs=[("requirements", "object")],
        ),
        _agent(
            "developer",
            "Developer Agent",
            "developer",
            "Implementa el trabajo asignado en el workspace autorizado, respetando las "
            "restricciones y reportando los cambios realizados.",
            {
                "type": "object",
                "properties": {
                    "files_modified": STRING_ARRAY,
                    "summary": {"type": "string"},
                    "diff": {"type": "string"},
                    "notes": STRING_ARRAY,
                    "errors": STRING_ARRAY,
                },
                "required": ["files_modified", "summary"],
            },
            {
                "files_modified": [],
                "summary": "Simulación: no se realizaron cambios reales (MockRuntime).",
                "diff": "",
                "notes": ["Ejecución simulada: configura un runtime real para modificar archivos"],
                "errors": [],
            },
            mode="workspace_write",
            write_paths=["."],
            inputs=[("instructions", "string"), ("requirements", "object")],
            tools=["read_file", "write_file", "shell"],
        ),
        _agent(
            "qa",
            "QA Agent",
            "qa",
            "Ejecuta pruebas reales, verifica criterios de aceptación e identifica regresiones.",
            {
                "type": "object",
                "properties": {
                    "tests": STRING_ARRAY,
                    "passed": {"type": "boolean"},
                    "failures": STRING_ARRAY,
                    "summary": {"type": "string"},
                },
                "required": ["tests", "passed"],
            },
            {
                "tests": [],
                "passed": True,
                "failures": [],
                "summary": "Simulación: sin pruebas ejecutadas",
            },
            inputs=[("acceptance_criteria", "array")],
            tools=["run_tests", "shell"],
        ),
        _agent(
            "code-reviewer",
            "Code Reviewer",
            "reviewer",
            "Revisa los cambios por corrección, mantenibilidad, seguridad y cumplimiento "
            "de requisitos. Aprueba o solicita cambios concretos.",
            {
                "type": "object",
                "properties": {
                    "approved": {"type": "boolean"},
                    "findings": STRING_ARRAY,
                    "required_changes": STRING_ARRAY,
                },
                "required": ["approved"],
            },
            {"approved": True, "findings": [], "required_changes": []},
            inputs=[("changes", "object")],
        ),
    ]


def install_default_agents(paths: ProjectPaths) -> int:
    """Crea los agentes por defecto que aún no existan. Nunca sobrescribe."""
    paths.ensure_layout()
    created = 0
    for agent in default_agents():
        path = paths.agent_path(agent.id)
        if path.exists():
            continue
        data = agent.model_dump(mode="json", exclude_none=True, by_alias=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        created += 1
    return created
