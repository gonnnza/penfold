"""Tests de los runtimes y la redacción de secretos."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from penfold.errors import ExecutionError, PermissionDeniedError
from penfold.runtimes.base import RuntimeContext
from penfold.runtimes.command import CommandRuntime
from penfold.runtimes.mock import MockRuntime
from penfold.runtimes.registry import available_runtimes, get_runtime
from penfold.runtimes.secrets import redact


def _context(tmp_path: Path, command: str, **options) -> RuntimeContext:
    return RuntimeContext(
        run_id="test-run",
        node_id="cmd",
        workspace=tmp_path,
        timeout=5,
        options={"command": command, **options},
    )


def test_registry_and_mock_are_explicitly_simulated() -> None:
    assert set(available_runtimes()) == {"mock", "command"}
    assert get_runtime("mock").simulated is True
    assert get_runtime("command").simulated is False

    async def scenario():
        result = await MockRuntime().execute(
            RuntimeContext(run_id="r", node_id="n", workspace=Path("."), inputs={"x": 1})
        )
        assert result.output["_simulated"] is True
        assert result.output["inputs"] == {"x": 1}

    asyncio.run(scenario())


def test_command_runtime_runs_real_process(tmp_path: Path) -> None:
    async def scenario():
        result = await CommandRuntime().execute(
            _context(tmp_path, "python -c \"print('hola real')\"")
        )
        assert result.output["exit_code"] == 0
        assert result.output["passed"] is True
        assert "hola real" in result.output["stdout"]
        assert len(result.artifacts) == 2

    asyncio.run(scenario())


def test_command_runtime_rejects_shell_and_traversal(tmp_path: Path) -> None:
    async def scenario():
        with pytest.raises(ExecutionError, match="shell"):
            await CommandRuntime().execute(_context(tmp_path, "echo hola; whoami"))
        with pytest.raises(PermissionDeniedError, match="workspace"):
            await CommandRuntime().execute(_context(tmp_path, "python --version", cwd="../../etc"))
        with pytest.raises(PermissionDeniedError, match="read_only"):
            await CommandRuntime().execute(
                _context(tmp_path, "python --version", permissions={"mode": "read_only"})
            )

    asyncio.run(scenario())


def test_redaction_of_env_values_and_patterns(monkeypatch) -> None:
    monkeypatch.setenv("PENFOLD_TEST_SECRET_TOKEN", "supersecretvalue123")
    text = "token=supersecretvalue123 key=sk-abcdefghijklmnopqrstuvwxyz"
    result = redact(text)
    assert "supersecretvalue123" not in result
    assert "***REDACTED***" in result
