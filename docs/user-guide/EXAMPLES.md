# Ejemplos de Penfold

Los ejemplos están disponibles en `examples/` como definiciones listas para
copiar en tu repositorio (también se instalan con `penfold init`). El MVP incluye
`examples/simple`, `examples/feature-development` y `examples/approval-demo`,
además de `examples/agents/`.

> Estado: los archivos YAML existen y son válidos para `schema_version: 1`.
> Los agentes usan MockRuntime de forma explícita: sustituye el runtime por un
> comando real cuando quieras ejecutar agentes de verdad.

## `examples/simple` — Input → Agent → Output

El ejemplo mínimo para comprobar que todo funciona. Contiene:

- `agents/product-analyst.yaml`: agente con `MockRuntime`, modo `read_only`,
  entrada `request` y salida JSON con `summary`.
- `workflows/hello.yaml`: tres nodos (`input`, `agent`, `output`) y dos aristas.

Definición simplificada del workflow:

```yaml
schema_version: 1
metadata:
  id: hello
  name: Hola Penfold
inputs:
  - id: request
    type: string
    required: true
nodes:
  - id: start
    type: input
    position: { x: 0, y: 0 }
    config: {}
  - id: analyst
    type: agent
    agent: product-analyst
    position: { x: 240, y: 0 }
    config:
      inputs:
        request: $inputs.request
  - id: end
    type: output
    position: { x: 480, y: 0 }
    config:
      format: json
      inputs:
        summary: $nodes.analyst.output.summary
edges:
  - { id: e1, source: start, target: analyst }
  - { id: e2, source: analyst, target: end }
```

Qué demuestra:

- Entradas declaradas en `inputs` y referenciadas con `$inputs.<id>`.
- Salida de un agente referenciada por `$nodes.<id>.output.<campo>`.
- `position` es decorativo: el motor solo usa `id`, `type` y `edges`.

Cómo probarlo: copia el ejemplo a tu repo, ejecuta `penfold init`, `penfold
start`, selecciona **Hola Penfold**, introduce un `request` y pulsa Ejecutar.

## `examples/feature-development` — caso JWT

Es el caso de uso de referencia de [PROJECT_SPEC.md](../PROJECT_SPEC.md):
«Añade autenticación JWT a la API, con refresh tokens y tests». Muestra un grafo
con varias responsabilidades, un nodo `command`, una condición con ramas, un
bucle con `max_iterations` y una aprobación humana.

### Flujo

```
Input(petición)
  → Agent product-analyst   (criterios de aceptación, read_only)
  → Agent tech-lead         (diseño, read_only)
  → Agent backend-engineer  (cambios, workspace_write)
  → Command pytest          (tests, sin shell)
  → Condition "¿pasan?"
       ├─ pass → Approval → Output(resumen)
       └─ fail → Agent fixer → (vuelta a Command, max_iterations: 3)
```

### Responsabilidades de los agentes

| Agente | Rol | Responsabilidad | Permisos |
|---|---|---|---|
| `product-analyst` | `analyst` | Criterios de aceptación y alcance. | `read_only` |
| `tech-lead` | `architect` | Decisiones de diseño (validación del token, TTL, refresh). | `read_only` |
| `backend-engineer` | `developer` | Implementar el cambio. | `workspace_write` |
| `test-engineer` | `tester` | Estrategia y ejecución de pruebas. | `read_only` |
| `fixer` | `developer` | Corregir fallos detectados; se ejecuta en bucle. | `workspace_write` |

En el ejemplo todos usan `MockRuntime` con salidas fijas para que la demo sea
determinista. El comando de tests es `python -m pytest -q` y se ejecuta con
`shlex.split`, sin shell.

### Fragmento representativo

```yaml
schema_version: 1
metadata:
  id: jwt-feature
  name: Desarrollar autenticación JWT
inputs:
  - id: request
    type: string
    required: true
nodes:
  - id: start
    type: input
    position: { x: 0, y: 200 }
    config: {}
  - id: analyst
    type: agent
    agent: product-analyst
    position: { x: 200, y: 200 }
    config:
      inputs:
        request: $inputs.request
  - id: tests
    type: command
    position: { x: 420, y: 200 }
    config:
      command: python -m pytest -q
      cwd: .
      timeout: 120
  - id: check
    type: condition
    position: { x: 640, y: 200 }
    config:
      inputs:
        result: $nodes.tests.output
      expression: { field: passed, op: eq, value: true }
  - id: review
    type: approval
    position: { x: 860, y: 100 }
    config:
      title: Revisar antes de continuar
      inputs:
        summary: $nodes.analyst.output.summary
  - id: end
    type: output
    position: { x: 1080, y: 100 }
    config:
      format: summary
      inputs:
        summary: $nodes.review.output
edges:
  - { id: e1, source: start, target: analyst }
  - { id: e2, source: analyst, target: tests }
  - { id: e3, source: tests, target: check }
  - { id: e4, source: check, target: review, source_handle: pass }
  - { id: e5, source: review, target: end }
```

El bucle de reintento (no mostrado arriba por brevedad) se añade con una arista
`source_handle: fail` hacia el agente `fixer` y otra de vuelta a `tests`, con
`config: {loop: true, max_iterations: 3}`. El ejemplo completo se entregará en
`examples/feature-development/workflows/jwt-feature.yaml`.

### Qué observar durante la demo

1. Los nodos pasan por `pending`, `ready`, `running` y `succeeded`.
2. El run se detiene en `waiting_approval`; la TUI muestra
   `RunDetail.approval` con título y datos.
3. Al aprobar, el flujo continúa hasta `completed` con `outputs`.
4. Los eventos llegan por SSE con `seq` creciente; al reiniciar la TUI se
   recuperan desde SQLite.
5. `NodeState.runtime` muestra `mock:<agente>` y `simulated: true`.

## Crear tus propios ejemplos

Copia la estructura de `examples/simple`, cambia `metadata.id` (también el
nombre del archivo YAML) y define tus agentes en `agents/`. Recuerda:

- `schema_version: 1`.
- Un archivo YAML por workflow y por agente.
- Sin expresiones ejecutables: solo `$inputs`, `$nodes` y literales.
- Define `outputs.schema` para que la salida del agente se valide.
- No guardes secretos en los YAML; usa variables de entorno.

Referencias: [WORKFLOW_SCHEMA.md](../../WORKFLOW_SCHEMA.md),
[EXTENDING.md](../development/EXTENDING.md),
[SECURITY.md](../../SECURITY.md).
