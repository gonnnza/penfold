# Roadmap de Penfold

Estado real al 2026-11-23: **prototipo 0.1 ejecutable de extremo a extremo**.
Fases 0–6 implementadas y verificadas; la fase 7 está parcialmente cubierta
(ejemplos, demo y tests ya funcionan; quedan CI, retención, revisión de
seguridad y release). Los hitos sin marcar **no** deben considerarse terminados.

## Fase 0 — Fundación del monorepo (HECHA)

- [x] `pyproject.toml` con Python `>=3.11`, `uv`, dependencias y entry point
      `penfold = penfold.cli.main:app`.
- [x] Contrato HTTP versionado en
      [docs/development/API_CONTRACT.md](docs/development/API_CONTRACT.md).
- [x] Estructura `src/penfold/{cli,server,execution,workflows,agents,runtimes,config,integrations}`
      y `web/`.
- [x] Documentación base de producto y arquitectura.
- [ ] CI mínima: `ruff`, `pytest`, `vitest`, build de `web/`.

## Fase 1 — Configuración, init y doctor (HECHA)

- [x] `penfold init`: crea `.orchestrator/` con `config.yaml`, `agents/`,
      `workflows/`, `state/`, `runs/`, `artifacts/` y SQLite inicializado.
- [x] Carga y validación de `config.yaml` con Pydantic v2.
- [x] `penfold doctor`: comprueba Python, dependencias, Git, Node, pnpm, puerto
      y proyecto inicializado.
- [x] Token local persistido en `.orchestrator/state/server.token` (0600).
- [x] `.gitignore` para `.orchestrator/state`, `runs` y `artifacts`.

## Fase 2 — Modelo de workflow y validación (HECHA)

- [x] Modelos Pydantic v2 de `WorkflowDefinition`, `WorkflowNode`,
      `WorkflowEdge` y `AgentDefinition`.
- [x] Carga/guardado de YAML con PyYAML y validación de contratos con
      `jsonschema`.
- [x] Reglas de validación de grafo: ids únicos, referencias existentes, nodos
      desconectados, ciclos sin límite y esquemas de salida.
- [x] Endpoints `/api/workflows` (GET/PUT/POST validate/DELETE) y
      `/api/agents` (GET/PUT).

## Fase 3 — Motor de ejecución (HECHA)

- [x] `GraphWorkflowEngine` con bucle de ejecución, checkpoints, cancelación,
      reanudación y aprobaciones, detrás del protocolo `ExecutionEngine`.
- [x] Los seis tipos de nodo: `input`, `agent`, `command`, `condition`,
      `approval`, `output`.
- [x] Resolución de mapeos `$inputs` / `$nodes`, operadores de condición,
      ramas `pass`/`fail`, unión explícita de ramas y bucles con
      `max_iterations` + límite global.
- [x] Persistencia en `runs`, `node_states`, `events` y `approvals`.

## Fase 4 — Runtimes (HECHA)

- [x] `MockRuntime` determinista con `mock.output` y marca `simulated: true`.
- [x] `CommandRuntime` con `shlex.split`, sin shell, `cwd` validado, timeout,
      redacción de secretos y reintentos.
- [x] Validación de `outputs.schema` y contrato `AgentRuntime.healthcheck` /
      `validate` / `execute` (ver
      [EXTENDING.md](docs/development/EXTENDING.md)).
- [x] Registro extensible de runtimes.

## Fase 5 — Servidor local y SSE (HECHA)

- [x] FastAPI + uvicorn en `127.0.0.1:8765` con token
      (`X-Penfold-Token` / `?token=` en SSE y artefactos).
- [x] Endpoints `/api/runs` (crear, listar, detalle, eventos, cancelar,
      reanudar, aprobar) y `/api/artifacts`.
- [x] SSE con replay por `after=<seq>` y heartbeat de 15 s.
- [x] Arranque con runs `running` → `paused` y recuperación desde checkpoints.

## Fase 6 — Editor visual (HECHA)

- [x] React 19 + TypeScript + Vite + `@xyflow/react` + zustand + lucide-react.
- [x] Crear/editar workflows con nodos y conexiones; inspector contextual.
- [x] Guardado **round-trip** a YAML (la UI edita el archivo, no una fuente
      privada).
- [x] Panel de ejecución con estados y eventos SSE; aprobación desde la UI.
- [x] Token en `localStorage` (también se consume el `?token=` de `penfold start`).
- [x] `pnpm build` servido por el backend.

## Fase 7 — Demo, endurecimiento y release 0.1 (EN CURSO)

- [x] Ejemplos `examples/simple`, `examples/feature-development` y
      `examples/approval-demo`.
- [x] Demo completa de la interfaz con Playwright (crear nodos, conectar,
      configurar, guardar, ejecutar, ver estados, recargar y recuperar).
- [x] Tests de integración (`pytest`, `httpx`, `pytest-asyncio`) y `vitest`
      (33 tests backend + 14 frontend + 2 E2E).
- [ ] Política de retención y purga de runs/artefactos.
- [ ] Revisión de seguridad final según [SECURITY.md](SECURITY.md) y release
      0.1.
- [ ] CI con `ruff`, `pytest`, `vitest` y build de `web/`.

## Fuera del roadmap de 0.1

- LangGraph u otros frameworks externos de grafos.
- Docker, contenedores o sandbox del SO.
- Nube, multiusuario, cuentas o sincronización.
- Integraciones concretas con CLIs de IA de terceros.
- Worktrees aislados por run conectados al motor (el helper Git existe pero no
  está integrado en la ejecución).
