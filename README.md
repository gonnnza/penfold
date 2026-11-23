# Penfold

> Orquestador visual de agentes de IA, local-first, para desarrollo de software.
> Versión 0.1 (MVP) — proyecto en construcción.

## El problema

Un equipo de agentes de IA que trabaja en un repositorio necesita algo más que una
conversación: necesita **flujos repetibles** con entradas declaradas, pasos con
responsabilidades claras, condiciones, revisión humana y un registro de lo que
pasó. Normalmente esa lógica acaba repartida entre prompts copiados, scripts
ad-hoc y conversaciones que no se pueden reproducir ni auditar.

Penfold convierte ese flujo en un **grafo editable visualmente** que vive en
archivos YAML dentro del propio repositorio, y lo ejecuta en tu máquina con un
motor local. La definición es legible y versionable; la ejecución es observable
y se puede reanudar.

## Qué NO es Penfold

- **No es un chatbot.** No hay una conversación abierta que "decida" qué hacer:
  el flujo está definido explícitamente y los datos viajan entre nodos mediante
  mapeos declarativos.
- **No es un wrapper de un CLI de IA.** No asume `claude`, `codex`, `aider` ni
  ningún producto concreto. Un agente puede usar `MockRuntime` (determinista)
  o `CommandRuntime` con el comando y los argumentos que tú declares
  explícitamente. No se inventan ni se adivinan flags de CLI.
- **No es un servicio en la nube.** No hay backend remoto, ni cuentas, ni
  sincronización. Todo se ejecuta en `127.0.0.1`.
- **No es un sandbox de seguridad.** Los modos de permiso son una guía para el
  motor y los agentes, no un aislamiento del sistema operativo (ver
  [SECURITY.md](SECURITY.md)).

## Principios

1. **Local-first**: el servidor escucha solo en `127.0.0.1:8765`; sin nube.
2. **YAML como fuente de la verdad**: los workflows y agentes son archivos
   versionables en `.orchestrator/`. La UI edita ese YAML; no hay un formato
   privado que se pierda al cerrar el editor.
3. **Definición visual ≠ ejecución**: la posición de los nodos es solo
   presentación; el motor ignora `position` y trabaja con ids, aristas y datos.
4. **Sin expresiones ejecutables**: los mapeos (`$inputs...`, `$nodes...`) son
   cadenas declarativas, nunca código evaluado.
5. **Ejecución observable**: cada cambio de estado emite un evento con número de
   secuencia, visible en la UI por SSE y persistido en SQLite.
6. **Reanudable**: los runs interrumpidos quedan pausados y se reanudan desde
   checkpoints sin repetir nodos ya exitosos.
7. **Revisión humana explícita**: el nodo `approval` detiene el run hasta que
   alguien aprueba, rechaza o modifica.

## Arquitectura resumida

```
   Terminal                       Navegador (React 19)
  `penfold`  ──arranca──▶   http://127.0.0.1:8765  (UI servida localmente)
     │                              │  X-Penfold-Token / ?token=
     │                              ▼
     └──────────▶  FastAPI (servidor local)  ◀──── SSE /api/runs/{id}/stream
                          │
                          ▼
                  ExecutionEngine (protocolo propio)
                          │
              Nodos: input | agent | command | condition
                     | approval | output
                          │
                  Runtimes: MockRuntime | CommandRuntime
                          │
                  Repositorio SQLite + archivos YAML/artefactos
                 (.orchestrator/state/penfold.db, .orchestrator/runs, ...)
```

Capas y decisiones: [ARCHITECTURE.md](ARCHITECTURE.md) y los
[ADR](docs/architecture/adr/). Contrato HTTP:
[docs/development/API_CONTRACT.md](docs/development/API_CONTRACT.md).

## Requisitos

- Python 3.11 o superior
- [uv](https://docs.astral.sh/uv/) (gestor de entornos y dependencias)
- Node 20 o superior
- [pnpm](https://pnpm.io/)

## Instalación

```bash
# Backend y CLI
uv sync --extra dev
uv run penfold --help

# Frontend (la UI se sirve desde el servidor local)
cd web
pnpm install
pnpm build
cd ..
```

## Inicio rápido

```bash
uv run penfold init      # crea .orchestrator/ con config, agentes y workflows
uv run penfold doctor    # comprueba entorno, puertos y consistencia
uv run penfold start     # arranca el servidor en 127.0.0.1:8765
```

Al arrancar, el servidor **imprime el token de acceso en la terminal**. Abre la
URL que se indica; la UI guarda el token en `localStorage` para no pedirlo en
cada recarga. El token también se conserva con permisos `0600` en
`.orchestrator/state/server.token` y se reutiliza en arranques posteriores. En
otra terminal puedes verificar el servicio con `GET /api/health`.

Guía completa: [docs/user-guide/GETTING_STARTED.md](docs/user-guide/GETTING_STARTED.md).

## Comandos CLI principales

| Comando | Qué hace |
|---|---|
| `penfold init` | Inicializa `.orchestrator/` en el repositorio de usuario. |
| `penfold doctor` | Diagnostica instalación, configuración y estado local. |
| `penfold start` | Arranca el servidor local y muestra URL y token. |
| `penfold run <workflow>` | Ejecuta un workflow desde la CLI (`-i clave=valor`, `--watch`). |
| `penfold runs` / `inspect <id>` / `logs <id>` | Lista y examina ejecuciones y eventos. |
| `penfold cancel <id>` / `resume <id>` | Cancela o reanuda un run. |
| `penfold workflow list` / `validate <id>` | Lista y valida definiciones YAML. |
| `penfold agent list` | Lista los agentes configurados. |

`penfold --help` es la fuente autoritativa de lo que ya está disponible en cada
momento.

## Estructura de persistencia

```
.orchestrator/
├── config.yaml              # configuración del proyecto (sin secretos)
├── agents/*.yaml            # definiciones de agentes
├── workflows/*.yaml         # definiciones de workflows (editables en la UI)
├── state/penfold.db         # SQLite: runs, node_states, events, approvals
├── runs/                    # datos/payloads por run
└── artifacts/               # artefactos generados
```

Solo se versionan `config.yaml`, `agents/` y `workflows/`; `state/`, `runs/` y
`artifacts/` se ignoran en Git. Detalles: [DATA_MODEL.md](DATA_MODEL.md).

## Ejemplo mínimo

Agente — `.orchestrator/agents/product-analyst.yaml` (simplificado; el esquema
completo está en [API_CONTRACT.md](docs/development/API_CONTRACT.md)):

```yaml
schema_version: 1
id: product-analyst
name: Product Analyst
description: Analiza requisitos y propone criterios de aceptación.
role: analyst
instructions: >
  Convierte la petición del usuario en criterios de aceptación claros.
runtime:
  type: mock
  provider: null
  model: null
  command: null
  args: []
tools: []
permissions:
  mode: read_only
  read_paths: []
  write_paths: []
  allowed_commands: []
inputs:
  - name: request
    type: string
    required: true
outputs:
  format: json
  schema:
    type: object
    required: [summary]
    properties:
      summary: { type: string }
timeout: 60
retries: 0
mock:
  output:
    summary: "Criterios de aceptación generados (simulado)."
```

Workflow — `.orchestrator/workflows/hello.yaml`:

```yaml
schema_version: 1
metadata:
  id: hello
  name: Hola Penfold
  description: Flujo mínimo Input -> Agent -> Output.
inputs:
  - id: request
    type: string
    required: true
nodes:
  - id: start
    type: input
    label: Entrada
    position: { x: 0, y: 0 }
    config: {}
  - id: analyst
    type: agent
    label: Analista
    agent: product-analyst
    position: { x: 240, y: 0 }
    config:
      inputs:
        request: $inputs.request
  - id: end
    type: output
    label: Resultado
    position: { x: 480, y: 0 }
    config:
      format: json
      inputs:
        summary: $nodes.analyst.output.summary
edges:
  - { id: e1, source: start, target: analyst }
  - { id: e2, source: analyst, target: end }
```

Cómo ejecutarlo: abre la UI, selecciona el workflow **Hola Penfold**, introduce
`request` y pulsa *Ejecutar*. Alternativamente, `POST /api/runs` con
`{"workflow_id": "hello", "inputs": {"request": "..."}}` y sigue el progreso
por `GET /api/runs/{id}/stream`. Los detalles de mapeos y validación están en
[WORKFLOW_SCHEMA.md](WORKFLOW_SCHEMA.md); más casos en
[docs/user-guide/EXAMPLES.md](docs/user-guide/EXAMPLES.md).

## Estado del MVP (0.1) y limitaciones conocidas

**Alcance previsto del MVP**: nodos `input`, `agent`, `command`, `condition`,
`approval` y `output`; `MockRuntime` y `CommandRuntime`; persistencia SQLite;
eventos SSE con reconexión por `after`; edición visual que **escribe YAML**;
autorizaciones humanas; token local.

**Todavía NO incluye**:

- LangGraph: el motor es un protocolo propio `ExecutionEngine` (ver
  [ADR-0002](docs/architecture/adr/0002-execution-engine-protocol.md)).
- Docker ni ningún tipo de contenedor/aislamiento.
- Nube, multiusuario, autenticación externa ni sincronización entre máquinas.
- Integraciones específicas con CLIs de IA (ni detección automática de sus
  opciones).
- Worktree aislado por run (se estudia como evolución futura).
- `AgentRuntime` para proveedores remotos más allá de `mock` y `command`.

**Estado de implementación**: MVP 0.1 en desarrollo; Fases 0 y 1 en curso (ver
[ROADMAP.md](ROADMAP.md)). Las capacidades descritas arriba definen el contrato
objetivo; consulta el estado de cada fase antes de darlas por terminadas.

## Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md) para el entorno (`uv` + `pnpm`), estilo
(`ruff`, línea 100), tests (`pytest`, `vitest`) y el procedimiento de ADRs. Para
extender el sistema: [docs/development/EXTENDING.md](docs/development/EXTENDING.md).

## Licencia

MIT — Copyright (c) 2026 Penfold contributors. Ver [LICENSE](LICENSE).
