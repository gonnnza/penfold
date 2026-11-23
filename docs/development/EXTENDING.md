# Extender Penfold

Guía para añadir nodos, runtimes y proveedores. Todo lo que se documente aquí
debe reflejarse también en
[API_CONTRACT.md](API_CONTRACT.md) y [WORKFLOW_SCHEMA.md](../../WORKFLOW_SCHEMA.md).

## 1. Agregar un tipo de nodo

Los tipos del MVP son `input`, `agent`, `command`, `condition`, `approval` y
`output`. Para añadir otro:

1. **Define la semántica**: entradas, salidas, transiciones de estado y eventos
   emitidos. Decide cómo se referencia su salida (`$nodes.<id>.output`).
2. **Esquema YAML**: añade el tipo a `NodeType` y las claves de `config` en la
   tabla de nodos de [API_CONTRACT.md](API_CONTRACT.md); documenta los campos en
   [WORKFLOW_SCHEMA.md](../../WORKFLOW_SCHEMA.md).
3. **Validación**: registra las reglas del nuevo tipo en `src/penfold/services`
   (ids, campos obligatorios, referencias). Un error de validación debe
   asociarse a un `path` y una severidad.
4. **Ejecutor**: implementa un `NodeExecutor` en `src/penfold/services` que:
   - resuelve `config.inputs` con los mapeos declarativos,
   - emite eventos antes y después de la ejecución,
   - actualiza `NodeState` (`pending → ready → running → succeeded | failed`),
   - respeta timeout, reintentos y cancelación.
5. **Registro**: da de alta el tipo en la fábrica de nodos del motor.
6. **Tests y docs**: tests de mapeos, estados y eventos; ejemplo en
   [EXAMPLES.md](../user-guide/EXAMPLES.md).

Un nodo nuevo no debería necesitar cambios en el servidor: el contrato HTTP
trabaja con la forma genérica de `WorkflowNode`.

## 2. Agregar un runtime (implementar `AgentRuntime`)

Un runtime es la forma en que un nodo `agent` obtiene su salida. La interfaz es
intercambiable y el motor solo depende de ella.

Firma conceptual de `AgentRuntime` (contrato estable en
`src/penfold/services/runtimes/base.py`; comprueba siempre el código antes de programar
contra ella):

```python
from abc import ABC, abstractmethod


class AgentRuntime(ABC):
    name: str = "base"
    simulated: bool = False

    async def execute(self, context: RuntimeContext) -> RuntimeResult:
        """Ejecuta la unidad de trabajo y devuelve una salida estructurada."""

    async def validate(self) -> None:
        """Comprueba que la configuración del runtime sea válida."""

    async def healthcheck(self) -> bool:
        """Comprueba que el runtime esté disponible."""
        return True
```

`RuntimeContext` agrupa `run_id`, `node_id`, `agent`, `inputs`, `workspace`,
`timeout`, `options`, `attempt` y un `cancel_event` de `asyncio`. La interfaz
expone tres operaciones — **`execute`, `validate`, `healthcheck`** — y es
independiente de proveedores y de LangGraph ([ADR-0002](../architecture/adr/0002-execution-engine-protocol.md)).

`RuntimeResult` incluye al menos:

```python
{
    "output": dict[str, Any],  # se valida contra agent.outputs.schema
    "logs": list[str],
    "artifacts": list[str],
    "metadata": dict[str, Any],
}
```

El campo `simulated` del runtime (y el `NodeState.simulated` resultante) indica
si la salida fue producida por `MockRuntime`.

### Advertencia: no asumir parámetros de CLI comunes

**No asumas** que el ejecutable de un agente acepta `--model`, `-p`, `--prompt`,
`--continue`, `--resume`, `--json`, `-y` ni ninguna otra opción "típica". Cada
herramienta de CLI de IA tiene las suyas y muchas no tienen equivalente. Un
runtime debe:

- usar **exactamente** `runtime.command` y `runtime.args` del
  `AgentDefinition`, tal como los declaró el usuario;
- pasar los datos de entrada por los mecanismos que el propio runtime define
  (p. ej. stdin o una posición concreta en `args`), nunca inventando flags;
- rechazar un agente cuyo `command` no esté en `permissions.allowed_commands`;
- documentar qué argumentos espera, sin rellenar por defecto parámetros de otros
  productos.

Esto es especialmente importante para `CommandRuntime`: Penfold es un
orquestador neutral, **no un wrapper de un CLI concreto**.

### Checklist para un runtime nuevo

- [ ] `validate()`: comprueba `runtime.type`, `command`, `args` y `outputs`.
- [ ] `healthcheck()`: rápido, sin efectos destructivos, con mensaje claro si
      falta el ejecutable.
- [ ] `execute()`: respeta `timeout`, `retries`, `permissions` y redacción de
      secretos.
- [ ] Sin shell: `shlex.split`, lista de argumentos, `cwd` relativo al repo.
- [ ] Salida validada contra JSON Schema; si falla, nodo `failed`.
- [ ] Registro en el mapa de runtimes por `runtime.type`.
- [ ] Tests: éxito, timeout, error de validación, secreto redactado, salud.

Los runtimes incluidos en el MVP son `MockRuntime` (determinista,
`simulated: true`) y `CommandRuntime` (proceso local sin shell).

## 3. Agregar un proveedor

Un "proveedor" identifica el origen de un agente (`runtime.provider` y
`runtime.model` en `AgentDefinition`). En el MVP el campo es informativo:
`MockRuntime` y `CommandRuntime` no necesitan un proveedor remoto.

Para añadir uno:

1. Decide si basta con un nuevo `AgentRuntime` (lo habitual) o si hace falta un
   adaptador en `src/penfold/integrations/`.
2. No asumas parámetros de CLI: declara en la definición del agente el `command`
   y los `args` exactos, o una variable de entorno con el punto de acceso.
3. Los secretos van en variables de entorno, nunca en YAML ni en la base de
   datos ([SECURITY.md](../../SECURITY.md)).
4. Registra el runtime/proveedor sin cambiar el contrato HTTP: el agente sigue
   siendo un `AgentDefinition` con `runtime.type` y campos opcionales.
5. Documenta el ejemplo en [EXAMPLES.md](../user-guide/EXAMPLES.md) y abre un
   ADR si introduces una nueva dependencia o un cambio arquitectónico.

## 4. Agregar un agente de ejemplo

1. Crea `.orchestrator/agents/<id>.yaml` con `schema_version: 1` y todos los
   campos del contrato.
2. Usa `MockRuntime` con `mock.output` fijo para que la demo sea determinista.
3. Define `outputs.schema` y `permissions.mode` apropiados a su responsabilidad.
4. Añade el agente a `examples/` y su papel a
   [PROJECT_SPEC.md](../../PROJECT_SPEC.md).

## Referencias

- [ADR-0002: ExecutionEngine](../architecture/adr/0002-execution-engine-protocol.md)
- [ADR-0003: formato YAML](../architecture/adr/0003-yaml-workflow-format.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
