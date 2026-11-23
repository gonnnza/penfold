"""Tests del motor: dependencias, contratos, condiciones, ciclos, aprobación y recuperación."""

from __future__ import annotations

import asyncio

from penfold.models.agent import AgentDefinition
from penfold.models.approval import ApprovalDecision
from penfold.models.execution import NodeState, NodeStatus, RunDetail, RunStatus
from penfold.models.workflow import WorkflowDefinition
from penfold.services.approval import AutoApproveGate
from penfold.services.workflow_templates import default_workflows


async def _finish(manager, run_id: str, timeout: float = 10.0):
    return await asyncio.wait_for(manager.wait(run_id), timeout=timeout)


def _raw(index: int) -> dict:
    return default_workflows()[index].model_dump(mode="json")


def test_sequential_run_uses_commands(components) -> None:
    *_, repository, events, manager = components

    async def scenario():
        run = await manager.start("simple", {"feature_description": "JWT"})
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.COMPLETED
        states = {node.node_id: node for node in final.nodes}
        assert states["analyst"].simulated is False
        assert states["analyst"].runtime == "command"
        assert states["tests"].simulated is False
        assert states["tests"].output["exit_code"] == 0
        assert final.outputs["data"]["requirements"]
        types = [event.type for event in repository.list_events(run.id)]
        assert "node_started" in types and "node_succeeded" in types and "run_finished" in types

    asyncio.run(scenario())


def test_contract_violation_retries_and_fails(components) -> None:
    project, config, agents, workflows, repository, events, manager = components
    bad = AgentDefinition.model_validate(
        {
            "id": "bad-output",
            "name": "Bad Output",
            "outputs": {
                "format": "json",
                "schema": {
                    "type": "object",
                    "required": ["passed"],
                    "properties": {"passed": {"type": "boolean"}},
                },
            },
            "retries": 1,
            "mock": {"output": {"unexpected": True}},
        }
    )
    agents.save(bad)
    raw = _raw(0)
    raw["metadata"]["id"] = "contract-test"
    raw["nodes"] = [raw["nodes"][0], raw["nodes"][1], raw["nodes"][3]]
    raw["nodes"][1]["type"] = "agent"
    raw["nodes"][1]["agent"] = "bad-output"
    raw["edges"] = [raw["edges"][0], {"id": "e-direct", "source": "analyst", "target": "output"}]
    raw["nodes"][2]["config"]["inputs"] = {}
    workflows.save(WorkflowDefinition.model_validate(raw))

    async def scenario():
        run = await manager.start("contract-test", {"feature_description": "x"})
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.FAILED
        state = final.node("analyst")
        assert state.status.value == "failed"
        assert state.attempts == 2  # intento inicial + 1 reintento
        assert "contrato" in state.error
        types = [event.type for event in repository.list_events(run.id)]
        assert "node_retry" in types

    asyncio.run(scenario())


def test_condition_and_bounded_correction_loop(components, failing_command_script) -> None:
    _, _, _, workflows, repository, _, manager = components
    raw = _raw(1)
    tests_node = next(node for node in raw["nodes"] if node["id"] == "tests")
    tests_node["config"]["command"] = failing_command_script
    workflows.save(WorkflowDefinition.model_validate(raw))

    async def scenario():
        run = await manager.start("feature-development", {"feature_description": "x"})
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.COMPLETED
        states = {node.node_id: node for node in final.nodes}
        assert states["tests"].attempts == 2
        assert states["developer"].iteration == 1
        assert states["developer"].attempts == 2
        assert states["check"].output["branch"] == "pass"
        types = [event.type for event in repository.list_events(run.id)]
        assert "loop_iteration" in types
        assert "loop_limit" not in types

    asyncio.run(scenario())


def test_loop_limit_stops_execution(components, project) -> None:
    _, _, _, workflows, repository, _, manager = components
    script = project.root / "always_fail.py"
    script.write_text("import sys\nprint('fail')\nsys.exit(1)\n", encoding="utf-8")
    raw = _raw(1)
    next(node for node in raw["nodes"] if node["id"] == "tests")["config"]["command"] = (
        "python always_fail.py"
    )
    workflows.save(WorkflowDefinition.model_validate(raw))

    async def scenario():
        run = await manager.start("feature-development", {"feature_description": "x"})
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.FAILED
        assert "Límite de iteraciones" in final.error
        assert any(event.type == "loop_limit" for event in repository.list_events(run.id))

    asyncio.run(scenario())


def test_approval_approve_and_reject(components) -> None:
    *_, repository, _, manager = components

    class RejectGate(AutoApproveGate):
        async def request(self, *args, **kwargs):
            return ApprovalDecision(decision="reject", note="rechazado en test")

    async def scenario():
        run = await manager.start(
            "approval-demo", {"feature_description": "x"}, gate=AutoApproveGate()
        )
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.COMPLETED
        assert final.node("approve").output["decision"] == "approve"
        assert any(event.type == "approval_requested" for event in repository.list_events(run.id))

        rejected = await manager.start(
            "approval-demo", {"feature_description": "x"}, gate=RejectGate()
        )
        final_rejected = await _finish(manager, rejected.id)
        assert final_rejected.status == RunStatus.FAILED
        assert "rechazada" in final_rejected.node("approve").error

    asyncio.run(scenario())


def test_cancel_interrupts_execution(components, project) -> None:
    _, _, _, workflows, repository, _, manager = components
    script = project.root / "slow_cancel.py"
    script.write_text("import time\ntime.sleep(3)\n", encoding="utf-8")
    raw = _raw(0)
    next(node for node in raw["nodes"] if node["id"] == "analyst")["config"]["command"] = (
        "python slow_cancel.py"
    )
    workflows.save(WorkflowDefinition.model_validate(raw))

    async def scenario():
        run = await manager.start("simple", {"feature_description": "x"})
        await asyncio.sleep(0.4)
        manager.cancel(run.id)
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.CANCELLED
        assert final.node("tests").status.value == "cancelled"

    asyncio.run(scenario())


def test_resume_keeps_succeeded_nodes(components) -> None:
    project, config, agents, workflows, repository, events, manager = components
    raw = _raw(0)
    raw["metadata"]["id"] = "resume-test"
    workflows.save(WorkflowDefinition.model_validate(raw))
    definition = workflows.get("resume-test")
    run = RunDetail(
        id="resume000001",
        workflow_id="resume-test",
        status=RunStatus.PAUSED,
        inputs={"feature_description": "x"},
        nodes=[NodeState(node_id=node.id) for node in definition.nodes],
    )
    run.node("start").status = NodeStatus.SUCCEEDED
    run.node("start").output = {"feature_description": "x"}
    repository.create_run(run)

    async def scenario():
        await manager.resume(run.id)
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.COMPLETED
        assert final.node("start").attempts == 0
        started = [
            event.node_id
            for event in repository.list_events(run.id)
            if event.type == "node_started"
        ]
        assert "start" not in started
        assert "analyst" in started

    asyncio.run(scenario())


def test_parallel_branches_join(components) -> None:
    _, _, _, workflows, _, _, manager = components
    raw = _raw(0)
    raw["metadata"]["id"] = "parallel-test"
    raw["nodes"] = [
        raw["nodes"][0],
        {
            "id": "left",
            "type": "agent",
            "agent": "product-analyst",
            "position": {"x": 1, "y": 2},
            "config": {"inputs": {"feature_description": "$inputs.feature_description"}},
        },
        {
            "id": "right",
            "type": "agent",
            "agent": "architect",
            "position": {"x": 1, "y": 3},
            "config": {"inputs": {"requirements": "$inputs.feature_description"}},
        },
        {
            "id": "output",
            "type": "output",
            "position": {"x": 9, "y": 9},
            "config": {"inputs": {"left": "$nodes.left.output", "right": "$nodes.right.output"}},
        },
    ]
    raw["edges"] = [
        {"id": "a", "source": "start", "target": "left"},
        {"id": "b", "source": "start", "target": "right"},
        {"id": "c", "source": "left", "target": "output"},
        {"id": "d", "source": "right", "target": "output"},
    ]
    workflows.save(WorkflowDefinition.model_validate(raw))

    async def scenario():
        run = await manager.start("parallel-test", {"feature_description": "x"})
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.COMPLETED
        assert "left" in final.outputs["data"] and "right" in final.outputs["data"]

    asyncio.run(scenario())


def test_command_timeout_and_read_only_permission(components, project) -> None:
    _, config, _, workflows, _, _, manager = components
    script = project.root / "slow.py"
    script.write_text("import time\ntime.sleep(3)\n", encoding="utf-8")
    raw = _raw(0)
    tests_node = next(node for node in raw["nodes"] if node["id"] == "tests")
    tests_node["config"] = {"command": "python slow.py", "timeout": 1}
    workflows.save(WorkflowDefinition.model_validate(raw))

    async def scenario():
        run = await manager.start("simple", {"feature_description": "x"})
        final = await _finish(manager, run.id)
        assert final.status == RunStatus.FAILED
        assert "Timeout" in final.node("tests").error

        config.security.default_permission_mode = "read_only"
        read_only_run = await manager.start("simple", {"feature_description": "x"})
        final_ro = await _finish(manager, read_only_run.id)
        assert final_ro.status == RunStatus.FAILED
        # En modo read_only falla el primer nodo command (analyst), antes que tests.
        assert "read_only" in final_ro.node("analyst").error

    asyncio.run(scenario())
