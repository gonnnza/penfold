"""Gestión del directorio de proyecto ``.orchestrator/``.

Todo el estado local vive dentro de esa carpeta. Los workflows y agentes son
archivos YAML versionables; la base de datos, logs y artefactos no deben
versionarse (se crea un ``.gitignore`` propio).
"""

from __future__ import annotations

import importlib.resources
import os
import stat
from pathlib import Path

import yaml

from penfold.config.models import ProjectConfig
from penfold.errors import NotFoundError, ProjectError

CONFIG_DIR = ".orchestrator"
CONFIG_FILE = "config.yaml"
DB_FILE = "state/penfold.db"
TOKEN_FILE = "state/server.token"

GITIGNORE_CONTENT = """# Estado efímero de Penfold: NO versionar
state/
runs/
artifacts/
*.token
*.log
"""

DEFAULT_CONFIG_YAML = """schema_version: 1
project:
  name: penfold-project
  description: ""
server:
  host: 127.0.0.1
  port: 8765
  auto_open_browser: true
execution:
  max_concurrency: 4
  default_timeout_seconds: 300
  max_retries: 2
  max_iterations: 3
  max_output_chars: 50000
security:
  default_permission_mode: workspace_write
  audit_sensitive_actions: true
defaults:
  runtime: mock
"""


class ProjectPaths:
    """Rutas absolutas y operaciones de inicialización de un proyecto Penfold."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.base = self.root / CONFIG_DIR

    @property
    def config_file(self) -> Path:
        return self.base / CONFIG_FILE

    @property
    def agents_dir(self) -> Path:
        return self.base / "agents"

    @property
    def workflows_dir(self) -> Path:
        return self.base / "workflows"

    @property
    def db_path(self) -> Path:
        return self.base / DB_FILE

    @property
    def token_path(self) -> Path:
        return self.base / TOKEN_FILE

    @property
    def runs_dir(self) -> Path:
        return self.base / "runs"

    @property
    def artifacts_dir(self) -> Path:
        return self.base / "artifacts"

    @property
    def static_dir(self) -> Path:
        """Build del frontend: junto al paquete Python o en el monorepo."""
        try:
            bundled = Path(
                importlib.resources.files("penfold").joinpath("static")  # type: ignore[arg-type]
            )
        except (ModuleNotFoundError, TypeError):  # pragma: no cover
            bundled = Path(__file__).resolve().parent.parent / "static"
        candidates = [
            bundled,
            self.root / "apps" / "server" / "static",
            Path(__file__).resolve().parents[3] / "apps" / "server" / "static",
        ]
        for candidate in candidates:
            if (candidate / "index.html").is_file():
                return candidate
        return candidates[0]

    def exists(self) -> bool:
        return self.config_file.is_file()

    def ensure_layout(self) -> None:
        for directory in (
            self.agents_dir,
            self.workflows_dir,
            self.db_path.parent,
            self.runs_dir,
            self.artifacts_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        gitignore = self.base / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(GITIGNORE_CONTENT, encoding="utf-8")

    def init(self, *, name: str | None = None, force: bool = False) -> ProjectConfig:
        if self.exists() and not force:
            raise ProjectError(
                f"Ya existe un proyecto Penfold en {self.base}. Usa --force para reinicializar "
                "(no sobrescribe agentes ni workflows existentes)."
            )
        self.ensure_layout()
        if not self.config_file.exists():
            content = DEFAULT_CONFIG_YAML
            if name:
                data = yaml.safe_load(content)
                data["project"]["name"] = name
                content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            self.config_file.write_text(content, encoding="utf-8")
        return self.load_config()

    def load_config(self) -> ProjectConfig:
        if not self.exists():
            raise ProjectError(
                f"No se encontró {self.config_file}. Ejecuta `penfold init` en este directorio."
            )
        try:
            raw = yaml.safe_load(self.config_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ProjectError(f"config.yaml inválido: {exc}") from exc
        if not isinstance(raw, dict):
            raise ProjectError("config.yaml debe contener un objeto YAML.")
        try:
            return ProjectConfig.model_validate(raw)
        except Exception as exc:  # Pydantic ValidationError
            raise ProjectError(f"config.yaml inválido: {exc}") from exc

    def save_config(self, config: ProjectConfig) -> None:
        self.ensure_layout()
        data = config.model_dump(mode="json", exclude_defaults=False)
        self.config_file.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

    def write_token(self, token: str) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(token, encoding="utf-8")
        try:
            os.chmod(self.token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:  # pragma: no cover - sistemas sin soporte de permisos
            pass

    def read_token(self) -> str | None:
        if not self.token_path.is_file():
            return None
        token = self.token_path.read_text(encoding="utf-8").strip()
        return token or None

    def require_project(self) -> ProjectConfig:
        if not self.exists():
            raise ProjectError(
                f"No se encontró un proyecto Penfold en {self.root}. Ejecuta `penfold init`."
            )
        return self.load_config()

    def workflow_path(self, workflow_id: str) -> Path:
        self._validate_id(workflow_id)
        return self.workflows_dir / f"{workflow_id}.yaml"

    def agent_path(self, agent_id: str) -> Path:
        self._validate_id(agent_id)
        return self.agents_dir / f"{agent_id}.yaml"

    @staticmethod
    def _validate_id(identifier: str) -> None:
        if not identifier or any(
            ch not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for ch in identifier.lower()
        ):
            raise NotFoundError(
                f"ID inválido: {identifier!r} (se permiten letras, números, - y _)."
            )


def find_project(start: Path | None = None) -> ProjectPaths:
    """Busca ``.orchestrator/config.yaml`` hacia arriba desde ``start``."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        paths = ProjectPaths(candidate)
        if paths.exists():
            return paths
    return ProjectPaths(current)
