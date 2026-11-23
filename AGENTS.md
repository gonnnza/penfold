# AGENTS.md — Instrucciones para agentes de código en Penfold

> **Documento vivo.** Se actualiza a medida que avanzamos en el código. Toda
> convención nueva, decisión o trampa descubierta se añade aquí y en
> [`skills.md`](skills.md). Si el código y este archivo discrepan, **manda el
> código** y hay que corregir este archivo en el mismo cambio.

## 1. Qué es Penfold (y qué no)

Orquestador visual **local-first** de agentes de IA para desarrollo de software,
en MVP 0.1. Un workflow es un grafo declarativo en YAML que vive en el repo; el
motor lo ejecuta en la máquina del usuario y expone progreso por SSE.

- ✅ Grafo YAML versionado en `.orchestrator/`, editado por una UI React que
  **guarda el YAML** (round-trip).
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
uv sync --extra dev                 # backend
cd web && pnpm install && cd ..     # frontend

# Backend
uv run pytest                       # tests
uv run ruff check .                 # lint (E, F, I, UP; line-length 100)
uv run ruff format --check .        # comprueba formato sin modificar
uv run ruff format .                # aplica formato
uv run penfold --help               # fuente autoritativa de comandos disponibles
uv run penfold init && uv run penfold doctor && uv run penfold start

# Frontend
cd web && pnpm test                 # Vitest
cd web && pnpm build                # tsc --noEmit && vite build
cd web && pnpm test:e2e             # Playwright
```

> El entry point real es `penfold.cli.main:app` (`pyproject.toml`). Comprueba
> siempre `penfold --help`: el README puede ir por delante o por detrás del código.

## 3. Mapa del repositorio

| Zona | Contenido |
|---|---|
| `src/penfold/cli/` | Typer + Rich: `init`, `doctor`, `start`, `run`, `runs`, `inspect`, `logs`, `cancel`, `resume`, grupos `workflow`/`agent`. |
| `src/penfold/server/` | FastAPI: `/api/health`, `/api/config`, `/api/workflows`, `/api/agents`, `/api/runs`, `/api/artifacts`, SSE `/api/runs/{id}/stream`. |
| `src/penfold/execution/` | `ExecutionEngine` propio: `engine`, `manager`, `models`, `context`, `events`, `repository`, `approval`. |
| `src/penfold/workflows/` | Modelos Pydantic, store YAML, plantillas, validador de grafo. |
| `src/penfold/agents/` | Modelos, store YAML, plantillas. |
| `src/penfold/runtimes/` | `base` (protocolo `AgentRuntime`), `mock`, `command`, `registry`, `secrets`. |
| `src/penfold/config/` | `paths` (localiza `.orchestrator/` y el build del frontend), modelos. |
| `src/penfold/integrations/git.py` | Helper Git no destructivo; **no conectado al motor** en 0.1. |
| `web/src/` | React 19 + TS + Vite + `@xyflow/react` + zustand + lucide. |
| `tests/` | pytest + httpx + pytest-asyncio. `web/src/*.test.ts` Vitest, `web/e2e/` Playwright. |
| `examples/` | `simple`, `feature-development`, `approval-demo`, agentes de ejemplo. |

Build del frontend: `web/dist`, con copias en `apps/server/static/` y
`src/penfold/static/`. `config/paths.py::static_dir` busca en ese orden. Si
cambias la UI, **recompila** con `cd web && pnpm build` y sincroniza las copias
que corresponda.

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
4. Pasa `uv run ruff check .`, `uv run pytest` y, si toca la UI,
   `cd web && pnpm test && pnpm build`.
5. Actualiza este `AGENTS.md` y `skills.md` con cualquier convención, decisión o
   trampa nueva. Añade entrada en el registro de cambios de ambos.

## 7. Trampas conocidas

- El build del frontend está duplicado en tres rutas; cambiar solo `web/` no
  actualiza lo que sirve el paquete instalado.
- `penfold start` imprime URL + token; la UI guarda el token en `localStorage`
  y también consume `?token=`. Sin token, los endpoints devuelven error.
- Los runs `running` interrumpidos pasan a `paused` al arrancar; se reanudan con
  `POST /api/runs/{id}/resume` sin repetir nodos exitosos.
- El helper `penfold.integrations.git` existe pero **no** está integrado en el
  motor: no lo llames desde la ejecución sin un ADR nuevo.
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
