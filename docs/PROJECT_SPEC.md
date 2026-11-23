# Especificación del proyecto Penfold

## Visión

Penfold es un orquestador visual **local-first** para equipos de agentes de IA
que trabajan en repositorios de software. Un workflow es un grafo declarativo,
legible y versionable que describe qué agentes intervienen, con qué datos, en
qué orden y bajo qué condiciones. Penfold ejecuta ese grafo en la máquina del
desarrollador, expone el progreso en tiempo real y conserva un registro
reanudable de cada run.

La visión es "Git para la lógica de tus agentes": la definición del flujo vive
junto al código, se revisa en pull requests y se reproduce igual en cualquier
máquina, sin depender de un servicio externo.

## Filosofía

- **Local primero**: sin nube; el servidor solo escucha en `127.0.0.1:8765`.
- **Datos sobre magia**: nodos conectados con mapeos explícitos, no prompts que
  "improvisan" el siguiente paso.
- **Archivos como interfaz**: YAML versionado con `schema_version: 1`; la UI es
  un editor de ese YAML, no un sustituto.
- **Humanos en el bucle**: el nodo `approval` es un ciudadano de primera clase.
- **Observabilidad y recuperación**: eventos numerados, checkpoints y runs
  pausados que se reanudan sin repetir trabajo ya completado.
- **Neutralidad de proveedor**: `ExecutionEngine` es un protocolo propio;
  `AgentRuntime` es una interfaz intercambiable. No se asume ningún CLI de IA.

## Caso de uso de referencia: desarrollar autenticación JWT

Es el escenario con el que se valida la demo. Un usuario pide:

> "Añade autenticación JWT a la API, con refresh tokens y tests."

El objetivo no es que un único agente lo resuelva todo, sino repartir el
trabajo en un grafo con responsabilidades explícitas y un punto de revisión
humana antes de dar por terminado:

```
Input(petición)
   │
   ▼
Agent: product-analyst ──▶ criterios de aceptación
   │
   ▼
Agent: tech-lead ──▶ diseño y decisiones (dónde se valida el token, TTL, refresh)
   │
   ▼
Agent: backend-engineer ──▶ cambios en el código (modo workspace_write)
   │
   ▼
Command: pytest ──▶ resultados de tests
   │
   ▼
Condition: tests pasan?
   ├── pass ─▶ Approval (revisión humana) ─▶ Output(resumen)
   └── fail ─▶ Agent: fixer ─▶ (vuelta a Command, max_iterations: 3)
```

### Responsabilidades de los agentes de ejemplo

| Agente | Rol | Responsabilidad | Permisos |
|---|---|---|---|
| `product-analyst` | `analyst` | Convertir la petición en criterios de aceptación y alcance. | `read_only` |
| `tech-lead` | `architect` | Proponer diseño, contratos y decisiones; no modifica código. | `read_only` |
| `backend-engineer` | `developer` | Implementar el cambio en el workspace. | `workspace_write` |
| `test-engineer` | `tester` | Definir y ejecutar la estrategia de pruebas (vía nodo `command`). | `read_only` |
| `fixer` | `developer` | Corregir fallos detectados por los tests; se ejecuta en bucle con límite. | `workspace_write` |
| `reviewer` | `reviewer` | Revisión final antes de la aprobación humana (opcional en la demo). | `read_only` |

En el MVP estos agentes pueden usar `MockRuntime` (salidas deterministas, para
la demo) o `CommandRuntime` (comando declarado explícitamente). Los ejemplos se
entregarán en `examples/feature-development` (ver
[docs/user-guide/EXAMPLES.md](docs/user-guide/EXAMPLES.md)).

## Alcance del MVP (0.1)

### Incluido

- CLI `penfold` con `init`, `doctor` y `start`.
- Servidor local FastAPI en `127.0.0.1:8765` con token mostrado en terminal y
  guardado en `localStorage` por la UI.
- Persistencia en `.orchestrator/`: `config.yaml`, `agents/*.yaml`,
  `workflows/*.yaml`, `state/penfold.db`, `runs/`, `artifacts/`.
- Seis tipos de nodo: `input`, `agent`, `command`, `condition`, `approval`,
  `output`, con branches `pass`/`fail` y bucles con `max_iterations`.
- `MockRuntime` (salidas simuladas y deterministas) y `CommandRuntime`
  (`shlex.split`, sin shell, `cwd` relativo al repo).
- `ExecutionEngine` propio: bucle de ejecución, checkpoints, cancelación,
  reanudación y espera de aprobaciones.
- Mapeos declarativos `$inputs.<name>` y `$nodes.<id>.output...`.
- Contratos de salida con JSON Schema.
- Validación de grafos (ids únicos, referencias existentes, nodos
  desconectados, ciclos infinitos, esquemas).
- Eventos SSE por run con reconexión mediante `after=<last event id>`.
- Editor visual React 19 + `@xyflow/react` que **guarda el YAML**; el archivo
  sigue siendo editable a mano.
- SQLite con tablas `runs`, `node_states`, `events`, `approvals`.
- Permisos declarativos por agente (`read_only`, `workspace_write`,
  `restricted`) y registro de auditoría en eventos.

### Fuera de alcance

- LangGraph u otro framework de grafos externo (hay un protocolo propio,
  [ADR-0002](docs/architecture/adr/0002-execution-engine-protocol.md)).
- Docker, contenedores o cualquier sandbox del sistema operativo.
- Nube, multiusuario, cuentas, RBAC remoto o sincronización.
- Integraciones concretas con productos de CLI de IA (ni adivinar sus flags).
- Worktrees aislados por run (evolución futura descrita en
  [ARCHITECTURE.md](ARCHITECTURE.md)).
- Runtimes remotos por API HTTP, streaming de tokens o herramientas avanzadas.
- Scheduler, cron o ejecución distribuida.

## Criterios de aceptación de la demo

La demo de MVP se considera correcta si, partiendo de un repositorio sin
`.orchestrator/`, se puede:

1. Ejecutar `penfold init` y obtener `.orchestrator/` con `config.yaml`,
   directorios `agents/`, `workflows/`, `state/`, `runs/`, `artifacts/` y el
   archivo `state/penfold.db` inicializado.
2. Ejecutar `penfold start`, ver la URL y el token en la terminal, abrir la UI
   y quedar autenticado al guardar el token en `localStorage`.
3. Crear un workflow nuevo en el editor visual con nodos **Input + Agent +
   Output** y conectarlo.
4. Configurar el nodo Input (nombre y tipo), el nodo Agent (agente y mapeos de
   entrada) y el nodo Output (mapeo de salida) desde la UI.
5. Guardar: el archivo `.orchestrator/workflows/<id>.yaml` se crea/actualiza con
   `schema_version: 1`, posiciones y conexiones; al recargar la UI se recupera
   el mismo grafo.
6. Ejecutar el workflow con `MockRuntime`, introduciendo un valor de entrada.
7. Ver en la UI los estados de los nodos (`pending`, `ready`, `running`,
   `succeeded`, …) y los eventos SSE a medida que avanza el run.
8. Cerrar y reabrir la UI: el historial de runs y el detalle (`RunDetail`) se
   recuperan desde SQLite, incluidos `NodeState` y eventos.

> Nota: los criterios 3–8 describen el flujo objetivo de la demo. Su estado de
> implementación se sigue en [ROADMAP.md](ROADMAP.md).

## Definiciones compartidas

Los nombres de entidades y campos de esta especificación coinciden con
[docs/development/API_CONTRACT.md](docs/development/API_CONTRACT.md):
`WorkflowDefinition`, `AgentDefinition`, `RunDetail`, `NodeState`, `RunEvent`,
`RunStatus`, `NodeStatus` y los tipos de nodo. Ante cualquier discrepancia,
manda el contrato HTTP.
