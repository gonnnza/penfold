# Esquema de workflows YAML

> Formato versionado del MVP 0.1 (`schema_version: 1`). Los nombres y tipos
> deben coincidir con [docs/development/API_CONTRACT.md](docs/development/API_CONTRACT.md).

## Principios

- Un workflow es **un archivo YAML** en `.orchestrator/workflows/<id>.yaml` con
  `schema_version: 1`. La UI lo edita; el motor lo lee.
- La definición es **declarativa**: los mapeos de datos son cadenas, nunca
  expresiones ejecutables.
- `position` es **solo visual**. El motor la ignora por completo: puedes
  reordenar el grafo sin cambiar la ejecución, y editar el YAML a mano sin que
  el editor se rompa.

## Estructura general

```yaml
schema_version: 1
metadata:
  id: string            # identificador único; también nombre de archivo
  name: string
  description: string   # opcional
inputs:
  - id: string
    type: string        # p. ej. string, number, boolean, object
    required: boolean   # opcional, por defecto false
    default: any        # opcional
nodes:
  - id: string
    type: input | agent | command | condition | approval | output
    label: string       # opcional
    agent: string | null  # obligatorio cuando type=agent
    description: string   # opcional
    position: { x: number, y: number }   # solo visual
    config: object      # específico por tipo (ver abajo)
edges:
  - id: string
    source: string
    target: string
    source_handle: default | pass | fail   # opcional, por defecto default
    target_handle: string                  # opcional
    label: string                          # opcional
    config:                                # opcional
      max_iterations: number
      loop: boolean
```

## Campos raíz

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `schema_version` | entero | sí | Debe ser `1` en el MVP. |
| `metadata.id` | string | sí | Id estable del workflow; coincide con el de la API. |
| `metadata.name` | string | sí | Nombre mostrado en la UI. |
| `metadata.description` | string | no | Descripción. |
| `inputs` | lista | sí | Entradas del workflow, declaradas aquí (no en el nodo `input`). Puede estar vacía. |
| `nodes` | lista | sí | Nodos del grafo. |
| `edges` | lista | sí | Conexiones; puede estar vacía en un grafo de un solo nodo. |

## Semántica de los seis tipos de nodo

### `input`

Expone las entradas declaradas en `inputs` al resto del grafo. Normalmente es
el primer nodo.

```yaml
config: {}
```

No tiene campos propios: los valores se referencian como `$inputs.<id>`.

### `agent`

Invoca a un `AgentDefinition` existente (`.orchestrator/agents/<id>.yaml`)
mediante su `AgentRuntime`. `agent` es un campo de primer nivel del nodo.

```yaml
nodes:
  - id: analyst
    type: agent
    agent: product-analyst
    position: { x: 240, y: 0 }
    config:
      inputs:                      # mapeo nombre -> valor resuelto
        request: $inputs.request
      timeout: 60                  # opcional; sobrescribe el del agente
      retries: 0                   # opcional; sobrescribe el del agente
      context:                     # opcional, string[]
        - $nodes.start.output
```

El resultado se guarda en `NodeState.output` y se referencia como
`$nodes.analyst.output` o `$nodes.analyst.output.<dotted.path>`. Se valida contra
`outputs.schema` del agente si está definido.

### `command`

Ejecuta un proceso local sin shell. El comando se divide con `shlex.split`, por
lo que **no hay expansión de variables ni metacaracteres de shell**.

```yaml
config:
  command: python -m pytest -q     # string, se aplica shlex.split
  cwd: .                           # ruta relativa dentro del repo
  timeout: 120
  inputs:
    request: $inputs.request
```

### `condition`

Evalúa una comparación simple y elige una de las dos ramas de salida.

```yaml
config:
  inputs:
    result: $nodes.tests.output
  expression:
    field: passed
    op: eq
    value: true
```

- `field`: ruta de acceso (puede ser punteada) al valor dentro de los `inputs`
  resueltos del nodo.
- `op`: uno de `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `in`, `exists`.
- `value`: literal contra el que se compara (no se evalúa código).

Resultado: las aristas salientes con `source_handle: pass` o `fail`. Si faltan
ramas, el grafo es inválido.

### `approval`

Detiene el run y espera una decisión humana. El run pasa a `waiting_approval` y
el nodo a `NodeState.status=waiting_approval`.

```yaml
config:
  title: Revisar cambios antes de publicar
  message: Revisa el diff y el resultado de los tests.
  inputs:
    summary: $nodes.analyst.output.summary
```

La decisión se envía con `POST /api/runs/{id}/approve` y cuerpo
`{decision: "approve" | "reject" | "modify", data?: any, note?: string}`.
`modify` reemplaza la salida del nodo con `data`.

### `output`

Compone `RunDetail.outputs`.

```yaml
config:
  format: json            # json | summary
  inputs:
    summary: $nodes.analyst.output.summary
    tests: $nodes.tests.output
```

## Mapeos declarativos

Los valores de `config.inputs` (y `context`) son cadenas. No se ejecutan como
código Python ni como JavaScript.

| Expresión | Significado |
|---|---|
| `$inputs.<name>` | Entrada del workflow declarada en `inputs` (o su `default`). |
| `$nodes.<id>.output` | Objeto de salida completo de ese nodo. |
| `$nodes.<id>.output.<dotted.path>` | Campo anidado de la salida. |
| `$nodes.<id>.status` | Estado del nodo (`NodeStatus`). |
| Cualquier otra cadena | Valor literal (se pasa tal cual). |

Un mapeo que referencia un nodo aún no ejecutado deja el nodo en `pending` hasta
que su dependencia termine. Las referencias a ids inexistentes son errores de
validación.

## Condiciones y operadores

| Operador | Semántica |
|---|---|
| `eq` / `ne` | Igualdad / desigualdad. |
| `gt` / `gte` | Mayor que / mayor o igual que (comparaciones numéricas). |
| `lt` / `lte` | Menor que / menor o igual que (comparaciones numéricas). |
| `contains` | El valor de `field` contiene `value` (cadena o lista). |
| `in` | El valor de `field` pertenece a la lista `value`. |
| `exists` | `field` está presente y no es `null`; ignora `value`. |

## Ramas `pass` / `fail`

```yaml
edges:
  - { id: e_ok,  source: check, target: done,  source_handle: pass }
  - { id: e_bad, source: check, target: fixer, source_handle: fail }
```

`source_handle: default` (o ausente) se usa para flujo secuencial normal. Las
condiciones y otros nodos con dos salidas usan `pass`/`fail`. Todas las aristas
salientes de un nodo con ramas deberían declarar su `source_handle`.

## Ciclos y `max_iterations`

Un ciclo se expresa con una arista que apunta a un nodo anterior y lleva
`loop: true` y `max_iterations`.

```yaml
edges:
  - id: retry
    source: check
    target: fixer
    source_handle: fail
    label: reintentar
    config:
      loop: true
      max_iterations: 3
```

- `NodeState.iteration` se incrementa en cada pasada por el ciclo.
- Al alcanzar `max_iterations`, la rama `fail` deja de tomarse y el run falla con
  un error explicativo (o sigue por otra arista `default` si se declara).
- Además existe un **límite global** de iteraciones, configurable en
  `config.yaml` (`execution.max_iterations`, por defecto 3). Actúa como valor
  por defecto y red de seguridad ante ciclos mal declarados: al superarse, el
  run pasa a `failed`.
- No se permiten aristas `loop: true` sin `max_iterations` positivo.

## Contratos de salida con JSON Schema

Cada agente declara `outputs.schema` (JSON Schema). El motor valida la salida
antes de publicarla en `$nodes.<id>.output`; si no cumple, el nodo pasa a
`failed` (y se aplican los `retries` configurados).

```yaml
outputs:
  format: json
  schema:
    type: object
    required: [summary, passed]
    properties:
      summary: { type: string }
      passed:  { type: boolean }
```

Esto hace que un cambio en la salida de un agente se detecte temprano y no se
propague silenciosamente por el grafo.

## Reglas de validación del grafo

La validación (`POST /api/workflows/validate`, y también en `PUT` con avisos)
produce `ValidationIssue { path, message, severity: error | warning }`:

| Regla | Severidad |
|---|---|
| `schema_version` presente e igual a `1`. | error |
| IDs de nodos y de aristas únicos dentro del workflow. | error |
| `metadata.id` presente y válido como nombre de archivo. | error |
| `edges.source` y `edges.target` referencian nodos existentes. | error |
| Un nodo no se conecta a sí mismo salvo que la arista sea `loop: true`. | error |
| Nodo `agent` con campo `agent` y archivo de agente existente. | error |
| Nodo `condition` con `expression` y operador válidos, y con ramas `pass`/`fail`. | error |
| Arista `loop: true` con `max_iterations` entero positivo. | error |
| Tipos de nodos y claves de `config` acordes con el contrato. | error |
| Referencias `$inputs` / `$nodes` a ids existentes. | error |
| Al menos un nodo `input` y un nodo `output` alcanzables en el flujo principal. | warning |
| Nodos desconectados (sin entradas ni salidas) o inalcanzables desde `input`. | warning |
| `outputs.schema` inválido como JSON Schema. | error |
| Ciclos infinitos sin `max_iterations` o sin límite global. | error |

`PUT /api/workflows/{id}` **guarda incluso con avisos/errores** y devuelve
`{ok: true, id, issues}` con HTTP 200; solo un esquema HTTP inválido da 422.
Esto permite guardar un trabajo a medias en la UI y corregirlo después.

## Ejemplo completo y ejecutable

`Input → Agent → Command → Condition → (pass → Output, fail → Agent con max_iterations: 3)`.
El agente `backend-engineer` se define aparte en
`.orchestrator/agents/backend-engineer.yaml` (con `MockRuntime` en el ejemplo).
Este archivo sería `.orchestrator/workflows/fix-tests.yaml`:

```yaml
schema_version: 1
metadata:
  id: fix-tests
  name: Arreglar tests
  description: Ejemplo de bucle con límite de iteraciones.
inputs:
  - id: request
    type: string
    required: true

nodes:
  - id: start
    type: input
    label: Petición
    position: { x: 0, y: 120 }
    config: {}

  - id: engineer
    type: agent
    label: Ingeniero
    agent: backend-engineer
    position: { x: 220, y: 120 }
    config:
      inputs:
        request: $inputs.request
      context:
        - $nodes.start.output
      timeout: 60
      retries: 1

  - id: tests
    type: command
    label: Ejecutar tests
    position: { x: 460, y: 120 }
    config:
      command: python -m pytest -q
      cwd: .
      timeout: 120
      inputs:
        request: $inputs.request

  - id: check
    type: condition
    label: ¿Pasan?
    position: { x: 700, y: 120 }
    config:
      inputs:
        result: $nodes.tests.output
      expression:
        field: passed
        op: eq
        value: true

  - id: done
    type: output
    label: Resultado
    position: { x: 940, y: 40 }
    config:
      format: json
      inputs:
        summary: $nodes.engineer.output.summary
        tests: $nodes.tests.output

  - id: repair
    type: agent
    label: Corrector
    agent: backend-engineer
    position: { x: 940, y: 240 }
    config:
      inputs:
        request: $inputs.request
        failure: $nodes.tests.output
      timeout: 60
      retries: 0

edges:
  - { id: e1, source: start,    target: engineer }
  - { id: e2, source: engineer, target: tests }
  - { id: e3, source: tests,    target: check }
  - { id: e4, source: check,    target: done,  source_handle: pass, label: ok }
  - id: e5
    source: check
    target: repair
    source_handle: fail
    label: reintentar
    config:
      loop: true
      max_iterations: 3
  - id: e6
    source: repair
    target: tests
    label: volver a probar
```

Notas sobre este ejemplo:

- `repair` y `engineer` usan el mismo agente, pero son nodos distintos con ids
  distintos; sus salidas se referencian por separado.
- El ciclo `check -(fail)-> repair -> tests -> check` está acotado por
  `max_iterations: 3` **y** por el límite global `execution.max_iterations`.
- `position` podría cambiarse libremente sin afectar a la ejecución.

## Cómo ejecutarlo

```bash
uv run penfold start
# En la UI: seleccionar "Arreglar tests", introducir request y pulsar Ejecutar.
```

Por API:

```bash
curl -X POST http://127.0.0.1:8765/api/runs \
  -H "X-Penfold-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"fix-tests","inputs":{"request":"Arregla los tests"}}'
```

El campo `id` devuelto sirve para seguir el run por SSE:
`GET /api/runs/{id}/stream?token=<token>`.
