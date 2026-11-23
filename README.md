<div align="center">

# Penfold

### Tus agentes de IA, en un grafo. En tu máquina. En Git.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Licencia](https://img.shields.io/badge/licencia-MIT-yellow)
![Versión](https://img.shields.io/badge/versi%C3%B3n-0.1.0-orange)
![Local-first](https://img.shields.io/badge/local--first-127.0.0.1%3A8765-green)
![Arquitectura](https://img.shields.io/badge/arquitectura-MVC-blueviolet)

**Orquestador visual local-first para equipos de agentes de IA que desarrollan software.**

Define flujos repetibles como grafos YAML versionables, edítalos en una interfaz
visual y ejecútalos localmente con progreso en tiempo real, revisión humana y
reanudación desde checkpoints.

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
- 🖱️ **Editor visual que escribe YAML** — round-trip real: lo que editas en la
  UI se guarda en el archivo. La posición de los nodos es solo presentación.
- 📡 **Ejecución observable** — SSE con replay por `after=<seq>` y heartbeat.
- ⏸️ **Reanudable** — los runs interrumpidos pasan a `paused` y continúan sin
  repetir nodos ya exitosos.
- ✋ **Humano al mando** — aprueba, rechaza o modifica antes de seguir.
- 🔒 **Solo local** — `127.0.0.1:8765` y token de acceso local (`0600`).

### Qué NO es

- ❌ Un chatbot: el flujo está definido, no improvisado.
- ❌ Un wrapper de un CLI de IA concreto.
- ❌ Un servicio en la nube: sin cuentas ni sincronización remota.
- ❌ Un sandbox: los permisos son declaración de intenciones, no aislamiento del
  SO (ver [SECURITY.md](SECURITY.md)).

## Cómo encaja

```
   Terminal                        Navegador (React 19)
  `penfold`  ── start ──▶   http://127.0.0.1:8765  (UI servida en local)
     │                             │  X-Penfold-Token / ?token=
     │                             ▼
     ├────────▶  FastAPI (views/)  ◀──── SSE /api/runs/{id}/stream
     │                             │
  `penfold tui`                    ▼
  (dashboard Rich) ──▶ services/ ◀── ExecutionEngine
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
El CLI y la TUI son adaptadores de entrada que llaman a los mismos services.

> 💡 **¿Sin navegador?** `penfold tui` abre un dashboard interactivo de terminal
> (workflows, agentes, runs y eventos en vivo). Habla directamente con los
> services: no necesita servidor HTTP ni token. La UI web sigue siendo la
> interfaz principal.

## Instalación

Requisitos: **Python 3.11+** y [uv](https://docs.astral.sh/uv/). Para la UI web
también hacen falta **Node 20+** y [pnpm](https://pnpm.io/). Para la TUI solo
hace falta Python.

```bash
# Backend, CLI y TUI
uv sync --extra dev
uv run penfold --help

# Frontend (la UI la sirve el servidor local)
cd web && pnpm install && pnpm build && cd ..
```

## Inicio rápido

```bash
uv run penfold init      # crea .orchestrator/ con config, agentes y workflows
uv run penfold doctor    # comprueba entorno, dependencias y puerto
uv run penfold start     # arranca en 127.0.0.1:8765 e imprime URL + token
```

Abre la URL que aparece en la terminal. La UI guarda el token en
`localStorage`; el token también se conserva con permisos `0600` en
`.orchestrator/state/server.token`. Comprueba el servicio con
`GET /api/health`.

Prefieres la terminal:

```bash
uv run penfold tui
```

Guía completa: [Getting started](docs/user-guide/GETTING_STARTED.md).

## Comandos

| Comando | Qué hace |
|---|---|
| `penfold init` | Inicializa `.orchestrator/` en el proyecto actual. |
| `penfold doctor` | Diagnostica instalación, configuración y estado local. |
| `penfold start` | Arranca el servidor local y abre la UI web. |
| `penfold tui` | Abre el dashboard interactivo de terminal. |
| `penfold run <workflow> -i clave=valor --watch` | Ejecuta un workflow desde la CLI. |
| `penfold runs` · `inspect <id>` · `logs <id> -f` | Lista y examina ejecuciones y eventos. |
| `penfold cancel <id>` · `resume <id>` | Cancela o reanuda un run desde su checkpoint. |
| `penfold workflow list` · `validate <id>` | Lista y valida definiciones YAML. |
| `penfold agent list` | Lista los agentes configurados. |

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

Ejecútalo desde la UI (selecciona **Hola Penfold**, rellena `request` y pulsa
*Ejecutar*), desde la terminal:

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
├── workflows/*.yaml         # definiciones de workflows (editables en la UI)
├── state/penfold.db         # SQLite: runs, node_states, events, approvals
├── runs/                    # payloads por run
└── artifacts/               # artefactos generados
```

Solo se versionan `config.yaml`, `agents/` y `workflows/`. Detalles:
[DATA_MODEL.md](docs/DATA_MODEL.md).

## Estado del MVP

**Fases 0–6 implementadas y verificadas** (fundación, config, validación,
motor, runtimes, servidor/SSE y editor visual). **Fase 7 en curso**: ejemplos,
demo y tests ya funcionan; quedan CI, retención y revisión de seguridad final
([ROADMAP.md](ROADMAP.md)).

Todavía **no** incluye: LangGraph, Docker o contenedores, nube/multiusuario,
integraciones concretas con CLIs de IA, worktrees aislados por run ni runtimes
remotos más allá de `mock` y `command`.

## Desarrollo

```bash
uv run pytest                       # backend
uv run ruff check .                 # lint (E, F, I, UP; línea 100)
uv run ruff format --check .        # formato
cd web && pnpm test && pnpm build   # frontend
```

El build de la UI se guarda una sola vez en el repo,
`apps/server/static/`; el wheel genera `penfold/static` desde ahí al
construirse ([ADR-0007](docs/architecture/adr/0007-single-static-build.md)).
Si cambias la UI, recompila y sincroniza esa carpeta.

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
