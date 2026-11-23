"""Integración mínima y real con repositorios Git.

Solo operaciones locales y no destructivas: consultar estado, diffs, crear
branches/worktrees y limpiar worktrees temporales. Nunca hace push, merge ni
deploy automático.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from penfold.errors import ExecutionError, NotFoundError


def _run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise ExecutionError("git no está instalado o no está en PATH.") from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover
        raise ExecutionError(f"Timeout ejecutando git {' '.join(args)}") from exc
    if check and result.returncode != 0:
        raise ExecutionError(f"git {' '.join(args)} falló: {result.stderr.strip()}")
    return result


def git_available() -> bool:
    return shutil.which("git") is not None


@dataclass
class RepoInfo:
    root: Path
    branch: str
    clean: bool
    changed_files: list[str]


class GitRepo:
    def __init__(self, path: Path):
        self.path = path.resolve()
        result = _run(self.path, "rev-parse", "--show-toplevel", check=False)
        if result.returncode != 0:
            raise NotFoundError(f"No se encontró un repositorio Git en {self.path}")
        self.root = Path(result.stdout.strip()).resolve()

    def info(self) -> RepoInfo:
        branch = _run(self.root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        changed = self.changed_files()
        return RepoInfo(root=self.root, branch=branch, clean=not changed, changed_files=changed)

    def changed_files(self) -> list[str]:
        output = _run(self.root, "status", "--porcelain=v1").stdout
        return [line[3:] for line in output.splitlines() if len(line) > 3]

    def diff(self, *, staged: bool = False) -> str:
        return _run(self.root, "diff", "--stat", *(["--cached"] if staged else [])).stdout

    def create_branch(self, name: str) -> str:
        if any(ch in name for ch in " ;&|`$><\n\r"):
            raise ExecutionError("Nombre de branch inválido.")
        _run(self.root, "checkout", "-b", name)
        return name

    def worktrees(self) -> list[str]:
        return _run(self.root, "worktree", "list", "--porcelain").stdout.splitlines()

    def add_worktree(self, directory: Path, branch: str | None = None) -> Path:
        target = directory.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        args = ["worktree", "add", "-b", branch or f"penfold-{Path(target).name}", str(target)]
        _run(self.root, *args)
        return target

    def remove_worktree(self, directory: Path, *, force: bool = False) -> None:
        target = directory.resolve()
        # No permitir borrar el worktree principal.
        if target == self.root:
            raise ExecutionError("No se puede eliminar el worktree principal.")
        _run(self.root, "worktree", "remove", *(["--force"] if force else []), str(target))
