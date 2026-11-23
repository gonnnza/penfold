# Modelo de datos de Penfold

> Esquema previsto para el MVP 0.1. Los nombres de entidades, campos y estados
> coinciden con [docs/development/API_CONTRACT.md](docs/development/API_CONTRACT.md).
> Ante cualquier discrepancia, manda el contrato HTTP.

## Almacenamiento

Penfold usa dos tipos de almacenamiento, todos bajo `.orchestrator/` en el
repositorio de usuario:

| Ubicación | Contenido | ¿Versionable? |
|---|---|---|
| `.orchestrator/config.yaml` | Configuración del proyecto (sin secretos). | Sí |
| `.orchestrator/agents/*.yaml` | `AgentDefinition` (un archivo por agente). | Sí |
| `.orchestrator/workflows/*.yaml` | `WorkflowDefinition` (un archivo por workflow). | Sí |
| `.orchestrator/state/penfold.db` | SQLite: runs, estados de nodo, eventos, aprobaciones. | No |
| `.orchestrator/state/server.token` | Token local del servidor (permisos `0600`). | No |
| `.orchestrator/runs/<run_id>/` | Payloads/intermedios del run. | No |
| `.orchestrator/artifacts/<run_id>/<name>` | Artefactos servidos por `/api/artifacts/...`. | No |

### `.gitignore` recomendado

```gitignore
.orchestrator/state/
.orchestrator/runs/
.orchestrator/artifacts/
```

`config.yaml`, `agents/` y `workflows/` **sí** se versionan: son la definición
del sistema. Los secretos nunca se guardan ahí, sino en variables de entorno
(ver [SECURITY.md](SECURITY.md)).

## Entidades de dominio

Estas son las formas JSON del contrato; la capa de repositorio las mapea a las
tablas SQLite.

### `WorkflowDefinition`

```ts
{
  schema_version: 1,
  metadata: { id: string, name: string, description?: string },
  inputs: Array<{ id: string, type: string, required?: boolean, default?: unknown }>,
  nodes: WorkflowNode[],   // {id, type, label?, agent?, description?, position, config}
  edges: WorkflowEdge[]    // {id, source, target, source_handle?, target_handle?, label?, config?}
}
```

Se persiste como YAML en `.orchestrator/workflows/<metadata.id>.yaml`. El motor
ignora `position`.

### `AgentDefinition`

```ts
{
  schema_version: 1, id, name, description, role, instructions,
  runtime: { type: "mock" | "command", provider?, model?, command?, args? },
  tools: string[],
  permissions: { mode, read_paths, write_paths, allowed_commands },
  inputs: Array<{ name, type, required? }>,
  outputs: { format: "json" | "text", schema?: object | null },
  timeout: number, retries: number,
  mock?: { output?: object }
}
```

Se persiste como YAML en `.orchestrator/agents/<id>.yaml`.

### `RunDetail`

```ts
{
  id, workflow_id, workflow_version,
  status: RunStatus,
  inputs: object,
  outputs: object | null,
  created_at, started_at, finished_at,
  error: string | null,
  approval: { node_id, title, data } | null,
  nodes: NodeState[]
}
```

### `NodeState`

```ts
{
  node_id, status: NodeStatus, iteration,
  started_at, finished_at, duration_ms,
  input: object | null, output: object | null,
  error: string | null, attempts,
  runtime: string | null, simulated: boolean
}
```

### `RunEvent`

```ts
{
  id: number, run_id, seq: number, type,
  level: "info" | "success" | "warning" | "error",
  node_id: string | null, message, data: object | null, timestamp
}
```

## Tablas SQLite

Archivo: `.orchestrator/state/penfold.db`. Las fechas son texto ISO-8601 en UTC;
los campos JSON se guardan como `TEXT` y se serializan en la capa de
repositorio.

### `runs`

| Columna | Tipo | Restricciones | Descripción |
|---|---|---|---|
| `id` | `TEXT` | `PRIMARY KEY` | Identificador del run. |
| `workflow_id` | `TEXT` | `NOT NULL`, indexada | `metadata.id` del workflow. |
| `workflow_version` | `INTEGER` | `NOT NULL DEFAULT 1` | Versión del workflow ejecutado. |
| `status` | `TEXT` | `NOT NULL`, indexada | `RunStatus`. |
| `inputs_json` | `TEXT` (JSON) | `NOT NULL DEFAULT '{}'` | Se expone como `RunDetail.inputs`. |
| `outputs_json` | `TEXT` (JSON) | nullable | Se expone como `RunDetail.outputs`. |
| `approval_json` | `TEXT` (JSON) | nullable | Se expone como `RunDetail.approval`. |
| `error` | `TEXT` | nullable | Mensaje de error si `failed`. |
| `created_at` | `TEXT` | `NOT NULL` | ISO-8601 UTC. |
| `started_at` | `TEXT` | nullable | ISO-8601 UTC. |
| `finished_at` | `TEXT` | nullable | ISO-8601 UTC. |
| `cancel_requested` | `INTEGER` | `NOT NULL DEFAULT 0` | Bandera de cancelación. |

Los nombres `*_json` son de almacenamiento: la API expone `inputs`, `outputs` y
`approval` con las formas del contrato. `nodes` en `RunDetail` se deriva de
`node_states`.

### `node_states`

| Columna | Tipo | Restricciones | Descripción |
|---|---|---|---|
| `run_id` | `TEXT` | `NOT NULL REFERENCES runs(id)`, parte de PK | Run propietario. |
| `node_id` | `TEXT` | `NOT NULL`, parte de PK | Id del nodo en el workflow. |
| `status` | `TEXT` | `NOT NULL` | `NodeStatus`. |
| `iteration` | `INTEGER` | `NOT NULL DEFAULT 0` | Iteración actual en bucles. |
| `started_at` | `TEXT` | nullable | ISO-8601 UTC. |
| `finished_at` | `TEXT` | nullable | ISO-8601 UTC. |
| `duration_ms` | `INTEGER` | nullable | Duración en milisegundos. |
| `input_json` | `TEXT` (JSON) | nullable | Se expone como `NodeState.input`. |
| `output_json` | `TEXT` (JSON) | nullable | Se expone como `NodeState.output`. |
| `error` | `TEXT` | nullable | Error del nodo. |
| `attempts` | `INTEGER` | `NOT NULL DEFAULT 0` | Intentos realizados. |
| `runtime` | `TEXT` | nullable | p. ej. `mock:product-analyst`. |
| `simulated` | `INTEGER` | `NOT NULL DEFAULT 0` | `1` si `MockRuntime` generó la salida. |

Clave primaria compuesta: `(run_id, node_id)`.

### `events`

| Columna | Tipo | Restricciones | Descripción |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Clave interna. |
| `run_id` | `TEXT` | `NOT NULL REFERENCES runs(id)`, indexada | Run propietario. |
| `seq` | `INTEGER` | `NOT NULL DEFAULT 0` | Secuencia monótona por run (para SSE `after`). |
| `type` | `TEXT` | `NOT NULL` | Tipo de evento. |
| `level` | `TEXT` | `NOT NULL DEFAULT 'info'` | `info`/`success`/`warning`/`error`. |
| `node_id` | `TEXT` | nullable | Nodo relacionado. |
| `message` | `TEXT` | `NOT NULL` | Mensaje legible (ya redactado). |
| `data_json` | `TEXT` (JSON) | nullable | Se expone como `RunEvent.data` (ya redactado). |
| `timestamp` | `TEXT` | `NOT NULL` | ISO-8601 UTC. |

Índice compuesto `ix_events_run_seq` sobre `(run_id, seq)` para el replay SSE.

### `approvals`

| Columna | Tipo | Restricciones | Descripción |
|---|---|---|---|
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | Clave interna. |
| `run_id` | `TEXT` | `NOT NULL REFERENCES runs(id)`, indexada | Run propietario. |
| `node_id` | `TEXT` | `NOT NULL` | Nodo `approval`. |
| `decision` | `TEXT` | nullable | `approve`/`reject`/`modify`. |
| `data_json` | `TEXT` (JSON) | nullable | Datos que se aprueban o reemplazo (`modify`). |
| `note` | `TEXT` | nullable | Nota del revisor. |
| `decided_at` | `TEXT` | nullable | ISO-8601 UTC de la decisión. |

La aprobación pendiente de un run se expone en `RunDetail.approval` a través de
`runs.approval_json`; la fila en `approvals` guarda el histórico de decisiones.

## Índices

```sql
-- implícitos (SQLAlchemy, index=True en las columnas)
CREATE INDEX ix_runs_workflow_id ON runs(workflow_id);
CREATE INDEX ix_runs_status      ON runs(status);
CREATE INDEX ix_events_run_id    ON events(run_id);
CREATE INDEX ix_approvals_run_id ON approvals(run_id);

-- explícito
CREATE INDEX ix_events_run_seq   ON events(run_id, seq);
```

Índices pensados para las consultas frecuentes: listar runs de un workflow
(`GET /api/runs?workflow_id=`), filtrar por estado, reproducir eventos desde un
`seq` y recuperar las decisiones de aprobación de un run.

## Artefactos en disco

- `.orchestrator/runs/<run_id>/`: entradas/salidas intermedias y logs del run.
- `.orchestrator/artifacts/<run_id>/<name>`: ficheros expuestos por
  `GET /api/artifacts/{run_id}/{name}`.

El nombre del artefacto se valida (sin `..`, sin separadores de ruta, sin rutas
absolutas) antes de leer del disco; ver [SECURITY.md](SECURITY.md). Ningún
artefacto se sirve fuera de `.orchestrator/artifacts/<run_id>/`.

## Checkpoints y runs recuperados

En 0.1 no hay una columna `checkpoint` separada: el "checkpoint" es el estado
persistido en `runs` y `node_states` (estado de cada nodo, `iteration`,
`output_json` y `attempts`). `GraphWorkflowEngine.prepare_resume()` reconstruye
el motor desde esas filas.

- Los nodos `succeeded` conservan su salida y no se reejecutan.
- Los nodos en `running`, `ready` o `waiting_approval` vuelven a `pending` al
  reanudar; la aprobación pendiente se limpia y el run pasa a `running`.
- `POST /api/runs/{id}/resume` solo acepta runs `paused` o `waiting_approval`.
- Los eventos no se eliminan al reanudar: la secuencia sigue incrementándose.

## Política de retención

Política prevista (la purga automática está planificada, aún no configurable en
`config.yaml` en 0.1):

- Conservar como máximo **100 runs por workflow** o **30 días**, lo que ocurra
  primero.
- Al purgar un run se borran en cascada `node_states`, `events` y `approvals`, y
  se eliminan sus directorios en `runs/` y `artifacts/`.
- Antes de purgar, la UI permite exportar el `RunDetail` y sus eventos como
  JSON (salida de `GET /api/runs/{id}` y `GET /api/runs/{id}/events`).
- La purga no toca definiciones YAML (`workflows/`, `agents/`, `config.yaml`).
- Los runs con una aprobación `pending` nunca se purgan automáticamente.

> La retención automática es parte del diseño; su implementación se planifica en
> fases posteriores ([ROADMAP.md](ROADMAP.md)).
