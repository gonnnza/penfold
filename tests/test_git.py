"""Tests de la integración Git real sobre un repositorio temporal."""

from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from penfold.cli.main import app as cli_app
from penfold.errors import NotFoundError
from penfold.models.git import RepoInfo
from penfold.services.git import GitService, git_available


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _make_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hola\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")


def test_git_repo_info_diff_and_worktrees(tmp_path: Path) -> None:
    if not git_available():
        return
    repo = tmp_path / "repo"
    _make_repo(repo)

    git_service = GitService(repo)
    info = git_service.info()
    assert isinstance(info, RepoInfo)
    assert info.branch == "main" and info.clean is True
    assert info.model_dump()["root"] == repo
    (repo / "new.txt").write_text("cambio\n", encoding="utf-8")
    assert "new.txt" in git_service.changed_files()
    assert git_service.info().clean is False

    worktree_dir = tmp_path / "wt-penfold"
    worktree = git_service.add_worktree(worktree_dir, "penfold-task")
    assert worktree.is_dir()
    assert any("penfold-task" in line for line in git_service.worktrees())
    git_service.remove_worktree(worktree)
    assert not worktree.exists()


def test_non_repo_raises(tmp_path: Path) -> None:
    try:
        GitService(tmp_path)
    except NotFoundError:
        return
    raise AssertionError("Se esperaba NotFoundError")


def test_git_cli_status_uses_service(tmp_path: Path) -> None:
    if not git_available():
        return
    repo = tmp_path / "repo"
    _make_repo(repo)
    (repo / "new.txt").write_text("cambio\n", encoding="utf-8")

    result = CliRunner().invoke(cli_app, ["git", "status", "--path", str(repo)])

    assert result.exit_code == 0, result.output
    assert "main" in result.output
    assert "new.txt" in result.output
