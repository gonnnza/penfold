"""Tests de la integración Git real sobre un repositorio temporal."""

from __future__ import annotations

import subprocess
from pathlib import Path

from penfold.errors import NotFoundError
from penfold.integrations.git import GitRepo, git_available


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_git_repo_info_diff_and_worktrees(tmp_path: Path) -> None:
    if not git_available():
        return
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hola\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")

    git_repo = GitRepo(repo)
    info = git_repo.info()
    assert info.branch == "main" and info.clean is True
    (repo / "new.txt").write_text("cambio\n", encoding="utf-8")
    assert "new.txt" in git_repo.changed_files()
    assert git_repo.info().clean is False

    worktree_dir = tmp_path / "wt-penfold"
    worktree = git_repo.add_worktree(worktree_dir, "penfold-task")
    assert worktree.is_dir()
    assert any("penfold-task" in line for line in git_repo.worktrees())
    git_repo.remove_worktree(worktree)
    assert not worktree.exists()


def test_non_repo_raises(tmp_path: Path) -> None:
    try:
        GitRepo(tmp_path)
    except NotFoundError:
        return
    raise AssertionError("Se esperaba NotFoundError")
