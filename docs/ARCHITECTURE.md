# Arquitectura de Penfold

## Visión general

Penfold separa estrictamente **la definición visual del flujo** de **su
ejecución**. El usuario edita un grafo en el navegador; Penfold persiste ese
grafo como YAML en el repositorio; el motor interpreta el YAML, no la posición
de los nodos en pantalla.

```
┌──────────────────────────────────────────────────────────────────────┐
│ CAPA 1 — CLI (Typer + Rich)                                          │
│   penfold init | doctor | start                                      │
│   Arranca el servidor, imprime URL + token.                          │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ arranque local
┌───────────────────────────────▼──────────────────────────────────────┐
│ CAPA 2 — Servidor local (FastAPI / uvicorn, 127.0.0.1:8765)         │
│   /api/health, /api/config, /api/workflows, /api/agents,            │
│   /api/runs, /api/artifacts, /api/runs/{id}/stream (SSE)            │
│   Autenticación por X-Penfold-Token (?token= para SSE)              │
└──────────┬─────────────────────────────────┬─────────────────────────┘
           │ servicios de dominio            │ eventos
┌──────────▼───────────────┐      ┌──────────▼─────────────────────────┐
│ CAPA 3 — Motor           │      │ Bus de eventos → SSE               │
│ ExecutionEngine          │      │ RunEvent {id, seq, type, level…}   │
│ validación, scheduling,  │      │ replay con after=<seq>             │
│ checkpoints, cancel,     │      │ heartbeat ": keep-alive" / 15 s    │
│ resume, approvals        │      └────────────────────────────────────┘
└──────────┬───────────────┘
           │ ejecuta
┌──────────▼───────────────┐
│ CAPA 4 — Nodos           │
│ input · agent · command  │
│ condition · approval · output │
└──────────┬───────────────┘
           │ AgentRuntime / CommandRuntime
┌──────────▼──────────────────────────────────────────────────────────┐
│ CAPA 5 — Runtimes                                                    │
│   MockRuntime (determinista) | CommandRuntime (shlex, sin shell)     │
│   timeout · reintentos · healthcheck · validación de salida          │
└──────────┬──────────────────────────────────────────────────────────┘
           │ repositorio
┌──────────▼──────────────────────────────────────────────────────────┐
│ CAPA 6 — Repositorio y almacenamiento                                │
│   Workflow/Agent YAML (.orchestrator/workflows, agents)              │
│   SQLAlchemy + SQLite (.orchestrator/state/penfold.db)                │
│   runs/ y artifacts/ en disco                                        │
└──────────────────────────────────────────────────────────────────────┘
```

Módulos bajo `src/penfold/`: `models/`, `services/`, `views/`, `cli/`, `config/`,
`integrations/`, `utils.py` (ver [ADR-0001](architecture/adr/0001-single-python-package.md)
y [ADR-0006](architecture/adr/0006-mvc-layering.md)).

## Patrón MVC (capas Model / Service / View)

Desde 0.1 el backend sigue un **MVC estricto** ([ADR-0006](architecture/adr/0006-mvc-layering.md)):

| Capa | Paquete | Contenido | Regla |
|---|---|---|---|
| **Model** | `src/penfold/models/` | Clases Pydantic, enums y alias de tipos (`workflow`, `agent`, `execution`, `config`, `runtime`). | **Solo declaración de clases.** Sin lógica de negocio, sin disco, sin HTTP. |
| **Service** | `src/penfold/services/` | Motor (`engine`), ciclo de vida (`manager`), validación, repositorio, stores, plantillas, runtimes y utilidades de dominio. | **Toda la lógica de negocio vive aquí.** No abre endpoints. |
| **View** | `src/penfold/views/` | Endpoints FastAPI (`app.py`), SSE y middleware de token (`auth.py`). | **Solo transporte.** Delega en services y serializa models. |

La CLI (`src/penfold/cli/`) es un **adaptador de entrada** equivalente a la
view: llama a los mismos services, no contiene lógica de negocio. Las
utilidades puras compartidas (p. ej. `utcnow`) viven en `utils.py` para que
ni models ni services dependan el uno del otro en dirección inversa.

Dependencias permitidas: `views/ → services/ → models/ → utils.py`. La
dirección contraria está prohibida.

## Separación definición visual / ejecución

| Definición visual (UI / YAML) | Ejecución (motor) |
|---|---|
| `nodes[].position: {x, y}` — solo dibujo | Se ignora por completo. |
| `nodes[].id`, `edges[].source/target/source_handle` | Grafo y orden de ejecución. |
| `config.inputs` con `$inputs` / `$nodes` | Resolución declarativa de datos. |
| `edges[].config.max_iterations` | Límite de bucle; además hay límite global. |
| `config.expression` de `condition` | Se evalúa con operadores permitidos. |
| `outputs.schema` (JSON Schema) | Validación de la salida del agente. |

Esto permite reordenar nodos en pantalla sin alterar la ejecución, y editar el
YAML a mano sin romper el editor. La UI es un **editor round-trip**: carga el
YAML, lo muestra como grafo y vuelve a serializarlo al guardar.

## Eventos SSE

- Cada transición relevante produce un `RunEvent` con `seq` monótono por run,
  `type`, `level` (`info` | `success` | `warning` | `error`), `node_id`,
  `message`, `data` y `timestamp`.
- `GET /api/runs/{id}/stream?after=<seq>&token=<token>` envía un
  `data: <RunEvent JSON>` por evento y mantiene la conexión abierta.
- Si se pierde la conexión, el cliente reconecta con el último `seq` recibido y
  el servidor reproduce los eventos perdidos desde `events`.
- Se envía un comentario `: keep-alive` cada 15 s.
- Los eventos también se pueden consultar con
  `GET /api/runs/{id}/events?after=`, útil para depuración y para reconstruir
  el estado de la UI sin SSE.

## Decisiones de diseño

| Decisión | Rationale | Detalle |
|---|---|---|
| Un único paquete Python `penfold` con submódulos | Simplicidad de desarrollo e importación | [ADR-0001](architecture/adr/0001-single-python-package.md) |
| MVC estricto: models / services / views | roles y dependencias unidireccionales explícitos | [ADR-0006](architecture/adr/0006-mvc-layering.md) |
| `ExecutionEngine` propio, sin LangGraph | Control total sobre checkpoints, cancelación y mapeos; LangGraph no aporta valor suficiente en 0.1 | [ADR-0002](architecture/adr/0002-execution-engine-protocol.md) |
| YAML versionado como fuente de la verdad | Legible, revisable en Git, sin base de datos propietaria para la definición | [ADR-0003](architecture/adr/0003-yaml-workflow-format.md) |
| SQLite local | Cero operaciones, reanudación y auditoría en la misma máquina | [ADR-0004](architecture/adr/0004-sqlite-local-persistence.md) |
| Token local + localhost | Seguridad mínima suficiente para un servicio de usuario único | [ADR-0005](architecture/adr/0005-local-token-auth.md) |
| Una sola copia versionada del build de la UI | Evita copias desincronizadas; el wheel se genera desde `apps/server/static` | [ADR-0007](architecture/adr/0007-single-static-build.md) |
| Dominio separado del transporte HTTP | Las mismas entidades se usan en CLI, motor y API | [API_CONTRACT.md](development/API_CONTRACT.md) |
| Sin shell en comandos | Evita inyección; `shlex.split` y lista de argumentos | [SECURITY.md](../SECURITY.md) |

## Flujo de una ejecución

1. **Crear**: `POST /api/runs` con `{workflow_id, inputs}` → `RunDetail` (201).
   El run queda `created` y se registran los `NodeState` iniciales (`pending`).
2. **Validar**: el motor valida el `WorkflowDefinition` y los agentes
   referenciados → `validating`. Si hay errores, run `failed`.
3. **Preparar**: se resuelven los mapeos (`$inputs`, `$nodes`) disponibles y se
   marcan los nodos listos como `ready` → `running`.
4. **Ejecutar nodos**: para cada nodo listo:
   - `input`: expone las entradas del run.
   - `agent`: `AgentRuntime.execute(...)`; valida `outputs.schema`; reintentos y
     timeout configurables; guarda `output`, `attempts`, `runtime`, `simulated`.
   - `command`: `shlex.split(command)` + `cwd` relativo; captura salida.
   - `condition`: evalúa `{field, op, value}` y elige arista `pass`/`fail`.
   - `approval`: el run pasa a `waiting_approval`; se crea fila en `approvals`;
     se espera `approve` (decisión `approve`/`reject`/`modify`).
   - `output`: compone `outputs` del run desde sus mapeos.
   Cada cambio emite eventos y actualiza `node_states` y `runs`.
5. **Bucles**: una arista con `loop: true` vuelve a un nodo anterior; el contador
   `iteration` por nodo y `max_iterations` de la arista limitan el bucle. Un
   límite global (`execution.max_iterations`) evita ciclos infinitos aunque
   falte `max_iterations`.
6. **Finalizar**: `completed` con `outputs`, o `failed` con `error`. La
   cancelación (`POST /api/runs/{id}/cancel`) marca el nodo en curso como
   `cancelled` y detiene el run entre nodos.
7. **Reanudar**: al arrancar el servidor, los runs `running` interrumpidos pasan
   a `paused`; `POST /api/runs/{id}/resume` reconstruye el estado desde
   `runs` / `node_states` sin reejecutar nodos `succeeded`.

## Modelo de permisos

Cada `AgentDefinition` declara:

```yaml
permissions:
  mode: read_only | workspace_write | restricted
  read_paths: [...]
  write_paths: [...]
  allowed_commands: [...]
```

- `read_only`: el agente solo consume datos; el motor no le concede escritura.
- `workspace_write`: puede proponer/escribir cambios dentro del workspace del
  repositorio, restringido a `write_paths`.
- `restricted`: solo `read_paths` / `allowed_commands` autorizados explícitamente.

Esto es una **declaración de intenciones** que el motor respeta al construir el
contexto y al decidir qué pasos puede ejecutar. **No es un sandbox**: un
`CommandRuntime` se ejecuta con los permisos del proceso de Penfold. Las
autorizaciones humanas (`approval`) y la auditoría en `events` complementan el
modelo. Ver [SECURITY.md](../SECURITY.md).

## Aislamiento con worktrees (evolución futura)

Para evitar que un agente modifique el árbol de trabajo del usuario, se estudia
que cada run use un **git worktree** temporal: el agente trabaja en una copia
aislada, los cambios se revisan en el nodo `approval` y solo se integran si se
aprueban. Esto no implementa un sandbox de seguridad, pero reduce el riesgo de
modificar archivos no deseados. Existe un módulo auxiliar local
(`penfold.integrations.git`) con operaciones Git no destructivas, pero **no está
conectado al motor en el MVP 0.1**; requiere decisiones adicionales sobre
limpieza, conflictos y artefactos (registrar un ADR nuevo).

## Más información

- [PROJECT_SPEC.md](PROJECT_SPEC.md)
- [DATA_MODEL.md](DATA_MODEL.md)
- [WORKFLOW_SCHEMA.md](../WORKFLOW_SCHEMA.md)
- [SECURITY.md](../SECURITY.md)
- [ADRs](architecture/adr/)
