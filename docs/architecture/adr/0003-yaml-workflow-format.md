# ADR-0003: Formato YAML versionado, posiciones separadas y mapeos declarativos

- Estado: propuesto
- Fecha: 2026
- Relacionado: [ADR-0002](0002-execution-engine-protocol.md)

## Contexto

El workflow es la unidad de trabajo de Penfold: se edita como YAML, se
guarda, se revisa en Git y se ejecuta. Necesitamos un formato que sea legible
por humanos y por el motor, que soporte la edición visual **round-trip** y que
no convierta el YAML en un lenguaje de programación encubierto.

Además, el formato admite coordenadas `x/y` opcionales, pero esas coordenadas
no tienen significado para la ejecución.

## Decisión

1. **YAML versionado** con `schema_version: 1`, un archivo por entidad:
   - `.orchestrator/workflows/<id>.yaml` → `WorkflowDefinition`
   - `.orchestrator/agents/<id>.yaml` → `AgentDefinition`
   - `.orchestrator/config.yaml` → configuración (sin secretos)

2. **Posiciones solo visuales**: `nodes[].position: {x, y}` se conserva para
   que el editor recupere el dibujo, pero el motor lo ignora. La semántica la
   dan `id`, `type`, `config` y `edges` (con `source_handle`).

3. **Mapeos declarativos, sin expresiones ejecutables**: los valores de
   `config.inputs` y `context` son cadenas con un conjunto cerrado de formas:
   - `$inputs.<name>`
   - `$nodes.<id>.output`
   - `$nodes.<id>.output.<dotted.path>`
   - `$nodes.<id>.status`
   - cualquier otra cadena se trata como literal.

   No se evalúa Python, JavaScript ni plantillas con lógica. Las condiciones
   usan un objeto `expression: {field, op, value}` con operadores
   predefinidos (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `in`,
   `exists`).

4. El YAML es la **fuente de la verdad**: la UI carga y guarda ese archivo; no
   existe una representación privada adicional en la base de datos.

Detalle completo: [WORKFLOW_SCHEMA.md](../../../WORKFLOW_SCHEMA.md).

## Consecuencias

### Positivas

- Los workflows se pueden revisar en diffs, editar a mano y copiar entre
  repositorios.
- Reordenar nodos no cambia la ejecución; regenerar posiciones no invalida un
  run.
- No hay riesgo de inyección de código desde el YAML: el motor solo resuelve
  paths y compara valores.
- Los errores de configuración se detectan con `jsonschema` antes de ejecutar.

### Negativas

- Los mapeos son menos expresivos que un lenguaje de plantillas: operaciones
  complejas requieren un nodo `command` o un agente.
- Cambiar `schema_version` obliga a definir migración y compatibilidad; por eso
  los cambios de esquema requieren discusión y un ADR nuevo.
- La UI debe ser cuidadosa al serializar para no reordenar claves ni perder
  campos desconocidos.

## Alternativas consideradas

1. **JSON en la base de datos**: más difícil de revisar y editar a mano; rompe el
   objetivo local-first de archivos versionables.
2. **DSL con expresiones tipo Jinja**: mayor flexibilidad, pero ejecuta lógica
   arbitraria y amplía la superficie de seguridad.
3. **Grafo solo en memoria + YAML como exportación**: la UI y el motor
   divergirían; se perdería la edición round-trip.

## Compatibilidad

Cualquier cambio del formato debe: mantener `schema_version`, actualizar
[API_CONTRACT.md](../../development/API_CONTRACT.md) y
[WORKFLOW_SCHEMA.md](../../../WORKFLOW_SCHEMA.md), y preservar la lectura de
archivos `schema_version: 1` o documentar una migración explícita.
