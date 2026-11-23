# AGENTS.md — Instrucciones para agentes de código en Penfold

> **Documento vivo.** Se actualiza a medida que avanzamos en el código. Toda
> convención nueva, decisión o trampa descubierta se añade aquí y en
> [`skills.md`](skills.md). Si el código y este archivo discrepan, **manda el
> código** y hay que corregir este archivo en el mismo cambio.

## 1. Qué es Penfold (y qué no)

Orquestador visual **local-first** de agentes de IA para desarrollo de software,
en MVP 0.1. Un workflow es un grafo declarativo en YAML que vive en el repo; el
motor lo ejecuta en la máquina del usuario y expone progreso por SSE.

- ✅ Grafo YAML versionado en `.orchestrator/`, editable directamente a mano.
- ✅ Ejecución observable (eventos `RunEvent` con `seq`), reanudable
  (checkpoints) con revisión humana (`approval`).
- ❌ **No** es un chatbot ni un wrapper de un CLI de IA: no se adivinan flags
  (`--model`, `-p`, `--continue`, …). Cada runtime declara su `command`/`args`.
- ❌ **No** es servicio en la nube: solo `127.0.0.1:8765` con token local.
- ❌ **No** es un sandbox: los permisos son declaración de intenciones, no
  aislamiento del SO. Sin Docker/contenedores.

Fuentes de verdad: [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md),
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/development/API_CONTRACT.md`](docs/development/API_CONTRACT.md) (contrato
HTTP — manda ante cualquier discrepancia),
[`WORKFLOW_SCHEMA.md`](WORKFLOW_SCHEMA.md),
[`docs/DATA_MODEL.md`](docs/DATA_MODEL.md),
[`SECURITY.md`](SECURITY.md).

## 2. Comandos rápidos

```bash
# Entorno
uv sync --extra dev                 # backend, CLI y TUI

# Backend
uv run pytest                       # tests
uv run ruff check .                 # lint (E, F, I, UP; line-length 100)
uv run ruff format --check .        # comprueba formato sin modificar
uv run ruff format .                # aplica formato
uv run penfold --help               # fuente autoritativa de comandos disponibles
uv run penfold init && uv run penfold doctor && uv run penfold tui

# Instalado como herramienta (utilizable desde cualquier carpeta)
uv tool install .          # o: uv tool install git+https://github.com/gonnnza/penfold.git
penfold --project /ruta/al/proyecto tui
```

> El entry point real es `penfold.cli.main:app` (`pyproject.toml`). Comprueba
> siempre `penfold --help`: el README puede ir por delante o por detrás del código.

## 3. Mapa del repositorio

| Zona | Contenido |
|---|---|
| `src/penfold/models/` | **MODEL**: solo declaración de clases Pydantic/enums (`workflow`, `agent`, `execution`, `config`, `runtime`, `git`, `approval`, `validation`). Sin lógica. |
| `src/penfold/services/` | **SERVICE**: toda la lógica de negocio (`engine`, `manager`, `validator`, `repository`, `stores`, `templates`, `approval`, `context`, `events`, `git`, `runtimes/`). |
| `src/penfold/views/` | **VIEW**: endpoints FastAPI, SSE y middleware de token (`app.py`, `auth.py`). 23 rutas. |
| `src/penfold/tui/` | **TUI**: dashboard Rich de terminal (`penfold tui`). Llama a services en proceso, sin HTTP ni token. |
| `src/penfold/cli/` | Typer + Rich: `init`, `doctor`, `start`, `tui`, `run`, `runs`, `inspect`, `logs`, `cancel`, `resume`, grupos `workflow`/`agent`/`git`. Adaptador de entrada. |
| `src/penfold/config/paths.py` | Infraestructura: localiza `.orchestrator/`. |
| `src/penfold/utils.py` | Utilidades puras compartidas (`utcnow`), neutras entre capas. |
| `tests/` | pytest + httpx + pytest-asyncio. |
| `examples/` | `simple`, `feature-development`, `approval-demo`, agentes de ejemplo. |

**No hay frontend web.** No existe `web/`, ni bundle estático, ni dependencias
Node/pnpm. La interfaz es la TUI (`penfold tui`) y la CLI; el servidor solo
expone la API REST y SSE.

## 4. Reglas de oro (invariantes)

1. **YAML es la fuente de la verdad.** La definición se persiste en
   `.orchestrator/workflows/*.yaml` y `agents/*.yaml` con `schema_version: 1`.
   Nunca inventes un formato privado ni escribas la definición solo en SQLite.
2. **`position` es solo visual.** Ninguna lógica del motor puede depender de las
   coordenadas de los nodos. El motor usa `id`, `edges` y datos.
3. **Sin expresiones ejecutables.** `$inputs.<name>` y `$nodes.<id>.output...`
   son cadenas declarativas resueltas por el motor; nunca `eval`/`exec`.
4. **Dominio separado del transporte.** Las entidades (`WorkflowDefinition`,
   `AgentDefinition`, `RunDetail`, `NodeState`, `RunEvent`, `RunStatus`,
   `NodeStatus`) se definen una vez y se usan en CLI, motor y API. Si cambian,
   actualiza **primero** `docs/development/API_CONTRACT.md`, luego código y docs.
5. **Neutralidad de proveedor.** Sin LangGraph, sin CLI de IA asumido, sin
   detección automática de flags. `ExecutionEngine` y `AgentRuntime` son
   protocolos propios.
6. **Comandos sin shell.** `shlex.split` + lista de args + `cwd` relativo al
   repo. Nada de `shell=True`.
7. **Sin secretos en archivos.** Variables de entorno; el token se guarda con
   `0600` en `.orchestrator/state/server.token`. Nada de secretos en YAML, DB,
   tests ni logs (se redactan).
8. **Idempotencia del motor.** Reanudar no repite nodos `succeeded`. Los eventos
   llevan `seq` monótono por run y se pueden reproducir con `after=<seq>`.
9. **Errores de API en inglés, docs en español.** `{"detail": "..."}` en inglés;
   identificadores de código en inglés; documentación y mensajes de CLI en
   español.
10. **Un solo paquete Python** `penfold` con submódulos. No crear nuevos
    paquetes distribuibles sin ADR (ADR-0001).
11. **Patrón MVC estricto (ADR-0006).** `models/` = solo declaración de clases;
    `services/` = toda la lógica de negocio; `views/` = endpoints HTTP. Nunca
    pongas lógica en un modelo ni abras endpoints desde un service. La CLI y la
    TUI son otros adaptadores que llaman a `services/`, igual que `views/`.

## 5. Convenciones de estilo

- Python 3.11+, Pydantic v2, typing moderno (`dict[str, Any]`, `X | None`).
- `ruff`: `line-length = 100`, reglas `E`, `F`, `I`, `UP`.
- Funciones pequeñas y puras en validación/mapeos; efectos (subprocess, SQLite,
  red) concentrados en runtimes y repositorio.
- Todo tipo de nodo nuevo: tests de resolución de entradas, transición de
  estados (`pending → ready → running → succeeded|failed`) y evento emitido.
- Todo runtime nuevo: tests de `execute`, `validate`, `healthcheck`, timeout y
  fallo de validación de salida.
- Los tests **no** dependen de red, de un CLI instalado ni de un puerto real:
  usa `MockRuntime` y la app FastAPI con `httpx`.
- Cambios arquitectónicos (paquetizado, motor, formato YAML, persistencia,
  autenticación) requieren ADR en `docs/architecture/adr/` con numeración
  consecutiva y enlace desde `docs/ARCHITECTURE.md`.

## 6. Flujo de trabajo para cambios

1. Entiende el estado real: lee el código y `ROADMAP.md` (los hitos sin marcar
   **no** están terminados).
2. Si afecta al contrato HTTP o al esquema YAML: edita primero el documento de
   contrato/esquema y después código + docs. Cambios de `schema_version`
   requieren discusión previa.
3. Implementa el cambio con tests.
4. Pasa `uv run ruff check .` y `uv run pytest`. No hay frontend que compilar.
5. Actualiza este `AGENTS.md` y `skills.md` con cualquier convención, decisión o
   trampa nueva. Añade entrada en el registro de cambios de ambos.

## 7. Trampas conocidas

- `penfold init` no crea agentes: los workflows de ejemplo usan nodos `command`
  y funcionan sin `.orchestrator/agents/*.yaml`. No reintroduzcas plantillas de
  agentes sin una decisión explícita; los tests usan sus propias fixtures.
- No hay interfaz web: el servidor solo expone API + SSE. Para usar el proyecto
  de forma interactiva, `penfold tui` (o los comandos de la CLI).
- `penfold start` imprime URL + token; el token se conserva en
  `.orchestrator/state/server.token` (`0600`). Sin token, los endpoints
  devuelven error.
- Los runs `running` interrumpidos pasan a `paused` al arrancar; se reanudan con
  `POST /api/runs/{id}/resume` sin repetir nodos exitosos.
- `penfold.services.git.GitService` existe pero **no** está integrado en el
  motor: no lo llames desde la ejecución sin un ADR nuevo. Su modelo es
  `penfold.models.git.RepoInfo` y su vista de solo lectura es `penfold git`.
- Parte de la documentación se reubicó en `docs/` (`ARCHITECTURE.md`,
  `PROJECT_SPEC.md`, `CONTRIBUTING.md`, `DATA_MODEL.md`), mientras `README.md`,
  `ROADMAP.md`, `SECURITY.md` y `WORKFLOW_SCHEMA.md` siguen en la raíz. Algunos
  enlaces del README aún apuntan a la raíz: verifica la ruta real antes de
  enlazar o mover archivos. Los ADR sí existen en `docs/architecture/adr/`
  (0001–0005).

## 8. Registro de cambios

| Fecha | Cambio | Nota |
|---|---|---|
| 2026-11-23 | Creación inicial de `AGENTS.md` y `skills.md` a partir del estado del repo (Fases 0–6 hechas, Fase 7 en curso). | — |
| 2026-11-23 | Ajuste de rutas de documentación a `docs/` y corrección de la nota sobre los ADR. | — |
| 2026-11-23 | Refactor a MVC: `models/` (solo clases), `services/` (lógica), `views/` (endpoints). ADR-0006. 33 tests pasan. | — |
| 2026-11-23 | Dashboard Rich de terminal (`penfold tui`, capa `tui/`). 35 tests pasan. | — |
| 2026-11-23 | Eliminada la copia duplicada `src/penfold/static/`; el wheel genera `penfold/static` desde `apps/server/static` con `force-include`. ADR-0007. | — |
| 2026-11-23 | Eliminado todo el frontend web (`web/`, bundle estático, rutas de UI, `force-include` y ADR-0007). La TUI y la CLI son la única interfaz. | — |
| 2026-11-23 | Git dividido en MVC: `models/git.py` (`RepoInfo`), `services/git.py` (`GitService`) y vista CLI `penfold git`. Sin cambios en el motor. | — |
| 2026-11-23 | Opción global `--project` y instalación con `uv tool install`; la CLI funciona desde cualquier carpeta. 39 tests pasan. | — |
| 2026-11-23 | Atajo `penfold .`: inicializa la carpeta si hace falta y abre la TUI. 40 tests pasan. | — |
| 2026-11-23 | Diagramas del workflow en terminal (`penfold workflow diagram`, opción `[5]` de la TUI). 43 tests pasan. | — |
| 2026-11-23 | Editor de workflows por terminal (`WorkflowEditor`, comandos `workflow new/add-node/connect/set/...` y opción `[6]` de la TUI). 47 tests pasan. | — |
| 2026-11-23 | Eliminados los agentes por defecto: `init` solo instala workflows, que ahora usan nodos `command`. Fixtures de tests con agentes mínimos. 47 tests pasan. | — |
| 2026-11-23 | `ApprovalDecision` y `ValidationIssue` movidos de `services/` a `models/`; siguen en services las tablas ORM y `EngineContext`. 47 tests pasan. | — |
| 2026-11-23 | La TUI limpia la pantalla en cada vista y deja un panel final al salir. 47 tests pasan. | — |
| 2026-11-23 | Interfaz full-screen estilo lazygit (`tui/lazy.py`, atajos j/k/Enter/n/d/r/q); `--classic` mantiene la anterior. 50 tests pasan. | — |
