"""Tests de la CLI ( Typer CliRunner )."""

from __future__ import annotations

from typer.testing import CliRunner

from penfold.cli.main import app
from penfold.config.paths import ProjectPaths

runner = CliRunner()


def test_init_creates_layout(tmp_path) -> None:
    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--name", "demo"])
    assert result.exit_code == 0, result.output
    paths = ProjectPaths(tmp_path)
    assert paths.config_file.is_file()
    assert len(list(paths.agents_dir.glob("*.yaml"))) == 6
    assert len(list(paths.workflows_dir.glob("*.yaml"))) == 3
    assert paths.db_path.is_file()
    assert (paths.base / ".gitignore").is_file()
    again = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert again.exit_code == 1


def test_cli_workflow_and_agent_commands(tmp_path, monkeypatch) -> None:
    assert runner.invoke(app, ["init", "--path", str(tmp_path)]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    listed = runner.invoke(app, ["workflow", "list"])
    assert listed.exit_code == 0 and "feature-development" in listed.output
    validated = runner.invoke(app, ["workflow", "validate", "simple"])
    assert validated.exit_code == 0 and "válido" in validated.output
    agents = runner.invoke(app, ["agent", "list"])
    assert agents.exit_code == 0 and "product-analyst" in agents.output
    runs = runner.invoke(app, ["runs"])
    assert runs.exit_code == 0


def test_cli_run_and_inspect(tmp_path, monkeypatch) -> None:
    assert runner.invoke(app, ["init", "--path", str(tmp_path)]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "simple", "-i", "feature_description=JWT demo"])
    assert result.exit_code == 0, result.output
    assert "completed" in result.output
    runs = runner.invoke(app, ["runs"]).output
    run_id = next(
        word
        for word in runs.split()
        if len(word) == 12 and all(c in "0123456789abcdef" for c in word)
    )
    inspected = runner.invoke(app, ["inspect", run_id])
    assert inspected.exit_code == 0 and "succeeded" in inspected.output
    logs = runner.invoke(app, ["logs", run_id])
    assert logs.exit_code == 0 and "run_finished" in logs.output
