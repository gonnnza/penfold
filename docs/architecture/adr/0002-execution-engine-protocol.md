# ADR-0002: Protocolo propio `ExecutionEngine`; LangGraph diferido

- Estado: propuesto
- Fecha: 2026
- Relacionado: [ADR-0001](0001-single-python-package.md),
  [ADR-0003](0003-yaml-workflow-format.md)

## Contexto

El MVP necesita ejecutar un grafo de nodos con:

- resolución declarativa de datos (`$inputs`, `$nodes.<id>.output...`),
- ramas `pass`/`fail` en condiciones,
- bucles con `max_iterations` y un límite global de pasos,
- checkpoints para reanudar sin reejecutar nodos `succeeded`,
- cancelación entre nodos y espera de aprobaciones humanas.

LangGraph u otros frameworks de grafos ofrecen parte de esto, pero imponen su
propio modelo de estado, serialización y semántica de nodos. En 0.1 necesitamos
control total sobre el formato YAML, los eventos y la recuperación, y no queremos
acoplar el producto a una librería externa antes de saber qué necesitamos de
ella.

## Decisión

Definir un **protocolo propio `ExecutionEngine`** en `src/penfold/services`,
con una interfaz intercambiable. El motor es responsable de:

- validar y compilar el `WorkflowDefinition` en un grafo ejecutable,
- decidir qué nodo se ejecuta a continuación,
- resolver mapeos de entrada,
- persistir `NodeState`, eventos y checkpoints,
- gestionar cancelación, aprobación y reanudación.

La interfaz es conceptualmente:

```python
class ExecutionEngine(Protocol):
    def validate(self, definition: WorkflowDefinition) -> ValidationResult: ...
    async def run(self, run: RunDetail, definition: WorkflowDefinition) -> None: ...
    async def cancel(self, run_id: str) -> None: ...
    async def resume(self, run_id: str) -> None: ...
    async def approve(self, run_id: str, decision: Decision) -> None: ...
```

Los nodos y los runtimes se conectan al motor mediante interfaces separadas
(`NodeExecutor`, `AgentRuntime`), de modo que cambiar de motor no obligue a
reescribir nodos ni agentes.

**LangGraph queda diferido** hasta que aporte un valor concreto (por ejemplo,
gestión avanzada de estado o subgrafos reutilizables) y exista un ADR que
justifique la migración.

## Consecuencias

### Positivas

- Sin dependencias externas pesadas en el MVP; stack reducido a lo ya elegido
  (Pydantic, SQLAlchemy, PyYAML, jsonschema…).
- Control exacto de la semántica de bucles, eventos y checkpoints; coincide con
  [WORKFLOW_SCHEMA.md](../../../WORKFLOW_SCHEMA.md) y el
  [API_CONTRACT.md](../../development/API_CONTRACT.md).
- La interfaz es intercambiable: otra implementación puede sustituir al motor
  si cumple el protocolo y se prueba contra la misma batería de tests.

### Negativas

- Hay que implementar y mantener planificación, ciclos y recuperación a mano.
- El protocolo es interno y puede cambiar durante 0.1; los nodos y runtimes
  deben acoplarse solo a la interfaz, no a detalles de la implementación.

## Alternativas consideradas

1. **Adoptar LangGraph desde el inicio**: más funcionalidad lista, pero estado
   y serialización ajenos al formato YAML y mayor acoplamiento.
2. **Usar un motor de flujos genérico (Temporal, Airflow)**: incompatible con
   el objetivo local-first y sin servidor externo.
3. **Scripts secuenciales sin grafo**: no soporta ramas, bucles ni
   reanudación.

## Revisión

Revisar este ADR cuando aparezca un caso de uso que el protocolo propio no
resuelva (subgrafos, paralelismo avanzado o persistencia distribuida). Cualquier
migración a LangGraph requiere un ADR nuevo y una capa de adaptación que
preserve el formato YAML y el contrato HTTP.
