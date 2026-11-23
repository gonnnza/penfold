<div align="center">

# Penfold

### Tus agentes de IA, en un grafo. En tu máquina. En Git.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Licencia](https://img.shields.io/badge/licencia-MIT-yellow)
![Versión](https://img.shields.io/badge/versi%C3%B3n-0.1.0-orange)
![Local-first](https://img.shields.io/badge/local--first-127.0.0.1%3A8765-green)
![Arquitectura](https://img.shields.io/badge/arquitectura-MVC-blueviolet)

**Orquestador local-first de agentes de IA que desarrollan software.**

Define flujos repetibles como grafos YAML versionables, edítalos a mano y
ejecútalos localmente con progreso en tiempo real, revisión humana y
reanudación desde checkpoints. Desde la terminal, con `penfold tui`.

[Instalación](#instalación) · [Inicio rápido](#inicio-rápido) ·
[Ejemplo](#ejemplo-mínimo) · [Documentación](#documentación)

</div>

---

## El problema

Un equipo de agentes necesita algo más que una conversación: necesita
**flujos repetibles** con entradas declaradas, responsabilidades claras,
condiciones, revisión humana y un registro auditable. Normalmente esa lógica
acaba repartida entre prompts copiados, scripts ad-hoc y chats que nadie puede
reproducir.

| Antes | Con Penfold |
|---|---|
| Prompts copiados entre repos | Workflows en `.orchestrator/workflows/*.yaml` |
| "El agente decide" el siguiente paso | Grafo explícito de nodos y aristas |
| Salidas opacas | Eventos con `seq`, persistidos y visibles por SSE |
| No se puede reanudar | Checkpoints + `penfold resume <id>` |
| Sin revisión | Nodo `approval` que detiene el run |

La definición es legible y versionable; la ejecución es observable y
reanudable. Es, en resumen, **Git para la lógica de tus agentes**.

## Qué te llevas

- 🧩 **Seis tipos de nodo** — `input`, `agent`, `command`, `condition`,
  `approval` y `output`.
- 🧠 **Neutralidad de proveedor** — `MockRuntime` determinista o
  `CommandRuntime` con el comando y los argumentos que tú declaras. Nada de
  adivinar flags de CLIs de IA.
- 🖥️ **Dashboard de terminal** — `penfold tui`: workflows, agentes, historial,
  ejecución en vivo y aprobaciones sin servidor ni token.
- 📡 **Ejecución observable** — API REST + SSE con replay por `after=<seq>`.
- ⏸️ **Reanudable** — los runs interrumpidos pasan a `paused` y continúan sin
  repetir nodos ya exitosos.
- ✋ **Humano al mando** — aprueba, rechaza o modifica antes de seguir.
- 🪴 **Git cuando hace falta** — `penfold git status|diff|worktrees`, con
  operaciones locales no destructivas.
- 🔒 **Solo local** — `127.0.0.1:8765` y token de acceso local (`0600`).

### Qué NO es

- ❌ Un chatbot: el flujo está definido, no improvisado.
- ❌ Un wrapper de un CLI de IA concreto.
- ❌ Un servicio en la nube: sin cuentas ni sincronización remota.
- ❌ Un sandbox: los permisos son declaración de intenciones, no aislamiento del
  SO (ver [SECURITY.md](SECURITY.md)).
- ❌ Un editor visual: el YAML se edita directamente en `.orchestrator/`.

## Cómo encaja

```
  `penfold tui`      `penfold ...`      `penfold start`
  (dashboard)        (comandos)         (API REST + SSE)
        │                  │                   │
        └────────┬─────────┴─────────┬─────────┘
                 ▼                   ▼
            services/            views/ (FastAPI)
     motor · validación · SSE · token
                 │
       ExecutionEngine + GitService
                 │
       input | agent | command | condition
           | approval | output
                 │
       MockRuntime | CommandRuntime
                 │
       SQLite + YAML + artefactos en .orchestrator/
```

La lógica vive en `services/`, los contratos de datos en `models/` y el
transporte HTTP en `views/` ([ADR-0006](docs/architecture/adr/0006-mvc-layering.md)).
La CLI y la TUI son adaptadores de entrada que llaman a los mismos services.
No hay interfaz web: el servidor solo expone la API.

## Instalación

Requisitos: **Python 3.11+** y [uv](https://docs.astral.sh/uv/). No hacen falta
Node ni pnpm.

```bash
uv sync --extra dev
uv run penfold --help
```

### Instalar como comando global

Para usar `penfold` desde **cualquier carpeta**, instálalo como herramienta:

```bash
uv tool install git+https://github.com/gonnnza/penfold.git
# o, desde un checkout local:
uv tool install .

penfold --version
```

## Inicio rápido desde cualquier carpeta

No hace falta estar dentro del repo de Penfold. En el directorio de tu proyecto:

```bash
cd /electrolux
penfold init      # crea .orchestrator/ con config, agentes y workflows
penfold doctor    # comprueba entorno, dependencias y puerto
penfold tui       # abre el dashboard interactivo de terminal
```

Todos los comandos buscan `.orchestrator/` en el directorio actual y, si no
está, en sus padres. También puedes apuntar explícitamente a otro proyecto
desde cualquier sitio con la opción global `--project`:

```bash
cd /tmp
penfold --project /electrolux workflow list
penfold --project /electrolux run simple -i "feature_description=JWT"
penfold --project /electrolux tui
```

Si usas el checkout en vez de la instalación global, sustituye `penfold` por
`uv run --project /ruta/a/penfold penfold`.

## Inicio rápido (desde el checkout)

```bash
uv run penfold init      # crea .orchestrator/ con config, agentes y workflows
uv run penfold doctor    # comprueba entorno, dependencias y puerto
uv run penfold tui       # abre el dashboard interactivo de terminal
```

En la TUI puedes listar workflows (`[1]`), ejecutar (`[2]`), consultar el
historial de runs (`[3]`) y ver agentes (`[4]`). Los eventos y los estados de
los nodos se actualizan en vivo; si aparece un nodo `approval`, tú decides.

Si necesitas la API: `uv run penfold start` arranca en `127.0.0.1:8765` e
imprime URL y token. El token también se conserva con permisos `0600` en
`.orchestrator/state/server.token`. Comprueba el servicio con
`GET /api/health`.

Guía completa: [Getting started](docs/user-guide/GETTING_STARTED.md).

## Comandos

| Comando | Qué hace |
|---|---|
| `penfold init` | Inicializa `.orchestrator/` en el proyecto actual. |
| `penfold doctor` | Diagnostica instalación, configuración y estado local. |
| `penfold tui` | Abre el dashboard interactivo de terminal. |
| `penfold start` | Arranca la API REST y SSE en localhost. |
| `penfold run <workflow> -i clave=valor --watch` | Ejecuta un workflow desde la CLI. |
| `penfold runs` · `inspect <id>` · `logs <id> -f` | Lista y examina ejecuciones y eventos. |
| `penfold cancel <id>` · `resume <id>` | Cancela o reanuda un run desde su checkpoint. |
| `penfold workflow list` · `validate <id>` | Lista y valida definiciones YAML. |
| `penfold agent list` | Lista los agentes configurados. |
| `penfold git status` · `diff` · `worktrees` | Consulta el repositorio Git local. |

`penfold --help` es la fuente autoritativa de lo disponible en cada momento.

## Ejemplo mínimo

Un agente simulado y un flujo `Input → Agent → Output`:

<details>
<summary>📄 <code>.orchestrator/agents/product-analyst.yaml</code></summary>

```yaml
schema_version: 1
id: product-analyst
name: Product Analyst
description: Analiza requisitos y propone criterios de aceptación.
role: analyst
instructions: Convierte la petición en criterios de aceptación claros.
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

</details>

<details>
<summary>📄 <code>.orchestrator/workflows/hello.yaml</code></summary>

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

</details>

Ejecútalo desde la TUI (`[2] Ejecutar`, escribe `hello`) o desde la terminal:

```bash
uv run penfold run hello -i request="Añadir login" --watch
```

o con `POST /api/runs` y siguiendo `GET /api/runs/{id}/stream`. Los mapeos
`$inputs` y `$nodes` son cadenas declarativas: nunca se evalúa código
([WORKFLOW_SCHEMA.md](WORKFLOW_SCHEMA.md),
[ejemplos](docs/user-guide/EXAMPLES.md)).

## Persistencia

```text
.orchestrator/
├── config.yaml              # configuración del proyecto (sin secretos)
├── agents/*.yaml            # definiciones de agentes
├── workflows/*.yaml         # definiciones de workflows
├── state/penfold.db         # SQLite: runs, node_states, events, approvals
├── runs/                    # payloads por run
└── artifacts/               # artefactos generados
```

Solo se versionan `config.yaml`, `agents/` y `workflows/`. Detalles:
[DATA_MODEL.md](docs/DATA_MODEL.md).

## Estado del MVP

**Fases 0–6 implementadas y verificadas** (fundación, config, validación,
motor, runtimes, servidor/SSE y TUI). **Fase 7 en curso**: ejemplos y tests ya
funcionan; quedan CI, retención y revisión de seguridad final
([ROADMAP.md](ROADMAP.md)).

Todavía **no** incluye: LangGraph, Docker o contenedores, nube/multiusuario,
integraciones concretas con CLIs de IA, editor visual, worktrees aislados por
run ni runtimes remotos más allá de `mock` y `command`.

## Desarrollo

```bash
uv run pytest                       # tests
uv run ruff check .                 # lint (E, F, I, UP; línea 100)
uv run ruff format --check .        # formato
```

Los cambios arquitectónicos requieren un ADR en `docs/architecture/adr/`.

## Documentación

- [Especificación del proyecto](docs/PROJECT_SPEC.md) ·
  [Arquitectura](docs/ARCHITECTURE.md) · [ADRs](docs/architecture/adr/)
- [Contrato HTTP](docs/development/API_CONTRACT.md) ·
  [Modelo de datos](docs/DATA_MODEL.md) ·
  [Cómo extender](docs/development/EXTENDING.md)
- [Primeros pasos](docs/user-guide/GETTING_STARTED.md) ·
  [Ejemplos](docs/user-guide/EXAMPLES.md) ·
  [Esquema de workflows](WORKFLOW_SCHEMA.md)
- [Seguridad](SECURITY.md) · [Contribuir](docs/CONTRIBUTING.md) ·
  [Roadmap](ROADMAP.md)

## Licencia

MIT — Copyright (c) 2026 Penfold contributors. Ver [LICENSE](LICENSE).
