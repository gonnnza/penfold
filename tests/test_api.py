"""Tests de integración de la API local (REST, token, aprobaciones, artefactos)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from penfold.server.app import create_app

TOKEN = "test-token"


@pytest.fixture
def client(components):
    project, config, *_ = components
    # El context manager mantiene vivo el event loop del portal de TestClient,
    # necesario para las tareas en segundo plano del motor.
    with TestClient(
        create_app(project, config, token=TOKEN), headers={"X-Penfold-Token": TOKEN}
    ) as test_client:
        yield test_client


def _wait_terminal(client: TestClient, run_id: str) -> dict:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["status"] in {"completed", "failed", "cancelled", "paused"}:
            return detail
        time.sleep(0.05)
    raise AssertionError("La ejecución no terminó a tiempo")


def test_health_is_public_but_api_requires_token(components) -> None:
    project, config, *_ = components
    app = create_app(project, config, token=TOKEN)
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/health").status_code == 200
        assert anonymous.get("/api/workflows").status_code == 401
    with TestClient(app, headers={"X-Penfold-Token": "wrong"}) as wrong:
        assert wrong.get("/api/workflows").status_code == 401


def test_workflow_crud_and_validation(client: TestClient) -> None:
    workflows = client.get("/api/workflows").json()
    assert {item["id"] for item in workflows} >= {"simple", "feature-development", "approval-demo"}
    definition = client.get("/api/workflows/simple").json()
    assert definition["schema_version"] == 1
    saved = client.put("/api/workflows/simple", json=definition)
    assert saved.status_code == 200 and saved.json()["ok"] is True
    bad = definition.copy()
    bad["nodes"] = [node for node in definition["nodes"] if node["id"] != "analyst"]
    result = client.post("/api/workflows/validate", json=bad).json()
    assert result["valid"] is False
    assert any(issue["severity"] == "error" for issue in result["issues"])
    assert client.get("/api/agents").json()
    assert client.get("/api/config").json()["project"]["name"] == "test-project"


def test_run_lifecycle_events_and_artifacts(client: TestClient) -> None:
    response = client.post(
        "/api/runs", json={"workflow_id": "simple", "inputs": {"feature_description": "JWT"}}
    )
    assert response.status_code == 201
    run_id = response.json()["id"]
    detail = _wait_terminal(client, run_id)
    assert detail["status"] == "completed"
    events = client.get(f"/api/runs/{run_id}/events").json()
    assert any(event["type"] == "run_finished" for event in events)
    assert client.get(f"/api/artifacts/{run_id}/tests.stdout.txt").status_code == 200
    # Path codificado: llega al endpoint y debe ser rechazado por is_relative_to.
    traversal = client.get(f"/api/artifacts/{run_id}/%2e%2e/%2e%2e/state/server.token")
    assert traversal.status_code in {404, 400}
    assert "token" not in traversal.text.lower()
    runs = client.get("/api/runs?workflow_id=simple").json()
    assert any(item["id"] == run_id for item in runs)
    assert client.get(f"/api/runs/{run_id}").json()["outputs"]["data"]["tests"]["passed"] is True


def test_approval_via_api(client: TestClient) -> None:
    response = client.post(
        "/api/runs", json={"workflow_id": "approval-demo", "inputs": {"feature_description": "x"}}
    )
    run_id = response.json()["id"]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["status"] == "waiting_approval":
            break
        time.sleep(0.05)
    else:
        raise AssertionError("No se solicitó aprobación")
    assert detail["approval"]["node_id"] == "approve"
    assert (
        client.post(f"/api/runs/{run_id}/approve", json={"decision": "approve"}).status_code == 200
    )
    assert _wait_terminal(client, run_id)["status"] == "completed"


def test_invalid_workflow_cannot_start(client: TestClient, components) -> None:
    _, _, _, workflows, *_ = components
    definition = workflows.get("simple").model_dump(mode="json")
    definition["metadata"]["id"] = "broken"
    definition["nodes"] = [node for node in definition["nodes"] if node["id"] != "analyst"]
    assert client.put("/api/workflows/broken", json=definition).status_code == 200
    response = client.post("/api/runs", json={"workflow_id": "broken", "inputs": {}})
    assert response.status_code == 422
    assert "inválido" in response.json()["detail"]
