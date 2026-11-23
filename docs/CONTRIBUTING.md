# Contribuir a Penfold

Gracias por ayudar. Penfold es un MVP en construcción: la mejor contribución es
pequeña, discutida y con tests.

## Setup

```bash
# Backend (Python 3.11+, uv)
uv sync --extra dev
uv run penfold --help

# Frontend (Node 20+, pnpm)
cd web
pnpm install
pnpm build
cd ..
```

No hace falta arrancar nada para desarrollar: los tests unitarios son
locales. Para probar la UI, `uv run penfold start` y abre la URL que imprime.

## Convenciones

- Español en documentación; inglés en identificadores de código y mensajes de
  error de API (`{"detail": "..."}`).
- Un único paquete Python `penfold` con submódulos internos. No crear nuevos
  paquetes distribuibles sin un ADR ([ADR-0001](docs/architecture/adr/0001-single-python-package.md)).
- Los nombres de entidades y campos **deben** coincidir con
  [docs/development/API_CONTRACT.md](docs/development/API_CONTRACT.md). Si cambia
  el contrato, actualiza primero ese archivo y luego el código y la doc.
- Sin secretos en archivos ni en tests: usa variables de entorno
  ([SECURITY.md](SECURITY.md)).
- `position` es solo visual; ninguna lógica del motor puede depender de él.

## Estilo

```bash
uv run ruff check .
uv run ruff format .        # si se habilita el formatter en el proyecto
```

- `ruff` con `line-length = 100`, reglas `E`, `F`, `I`, `UP`.
- Typing moderno (`dict[str, Any]`, `X | None`), Pydantic v2 para modelos.
- Preferir funciones pequeñas y puras (sin efectos) en la validación y en los
  mapeos; los efectos (subprocess, SQLite, red) se concentran en runtimes y
  repositorio.

## Tests

```bash
# Backend
uv run pytest

# Frontend
cd web && pnpm test       # Vitest
cd web && pnpm build      # comprueba que la UI compila
```

- Todo tipo de nodo nuevo necesita tests de: resolución de entradas,
  transición de estados y evento emitido.
- Todo runtime nuevo necesita tests de `execute`, `validate` y `healthcheck`,
  incluyendo timeout y fallo de validación de salida.
- Los contratos HTTP se prueban con `httpx` contra la app FastAPI.
- Los tests no deben depender de red, de un CLI de IA instalado ni de un
  puerto real; usa `MockRuntime`.

## Cómo agregar un tipo de nodo

1. Define su forma YAML en [WORKFLOW_SCHEMA.md](WORKFLOW_SCHEMA.md) y su
   `config` en la tabla de nodos de
   [API_CONTRACT.md](docs/development/API_CONTRACT.md).
2. Añade el valor al tipo `NodeType` y las reglas de validación
   (`src/penfold/workflows`).
3. Implementa el ejecutor del nodo en `src/penfold/execution` con transiciones
   `pending → ready → running → succeeded|failed`, emisión de `RunEvent` y
   actualización de `NodeState`.
4. Si el nodo produce salida, documenta cómo se referencia con
   `$nodes.<id>.output`.
5. Añade tests y un ejemplo en [docs/user-guide/EXAMPLES.md](docs/user-guide/EXAMPLES.md).

## Cómo agregar un runtime

Implementa el protocolo `AgentRuntime` (`execute` / `validate` / `healthcheck`)
en `src/penfold/runtimes` y regístralo. La firma conceptual y las advertencias
están en [docs/development/EXTENDING.md](docs/development/EXTENDING.md).

- No asumas parámetros de CLI comunes (`--model`, `-p`, `--prompt`, `--continue`,
  etc.). Cada runtime declara su `command` y `args` explícitamente.
- El runtime debe respetar `timeout`, `retries`, `permissions` y la redacción de
  secretos.
- Un runtime que no esté listo debe fallar `healthcheck` con un mensaje claro,
  no bloquear el arranque del servidor.

## Cómo agregar un agente

1. Crea `.orchestrator/agents/<id>.yaml` con `schema_version: 1` y los campos
   del contrato (`role`, `instructions`, `runtime`, `permissions`, `inputs`,
   `outputs`, `timeout`, `retries`).
2. Define `outputs.schema` con JSON Schema para que el motor valide la salida.
3. Para la demo, usa `MockRuntime` con `mock.output` determinista.
4. Añade el agente a `examples/` si es reutilizable y documenta su
   responsabilidad en [PROJECT_SPEC.md](PROJECT_SPEC.md).

## ADRs

Los cambios arquitectónicos (paquetizado, motor, formato YAML, persistencia,
autenticación) requieren un ADR en
[docs/architecture/adr/](docs/architecture/adr/): copia el formato de los
existentes, numeración consecutiva, estados `propuesto | aceptado | obsoleto` y
un enlace desde [ARCHITECTURE.md](ARCHITECTURE.md).

## Pull requests

- Un propósito por PR; incluye qué cambia, cómo probarlo y qué no incluye.
- Marca en la descripción si el cambio afecta al contrato HTTP o al esquema
  YAML (cambios de `schema_version` requieren discusión previa).
- No marques una fase del [ROADMAP.md](ROADMAP.md) como terminada hasta que sus
  entregables tengan tests y documentación.
