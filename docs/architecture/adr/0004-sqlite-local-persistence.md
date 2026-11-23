# ADR-0004: Persistencia local con SQLite, checkpoints y runs recuperados

- Estado: propuesto
- Fecha: 2026
- Relacionado: [ADR-0003](0003-yaml-workflow-format.md),
  [ADR-0005](0005-local-token-auth.md)

## Contexto

Penfold debe conservar el historial de ejecuciones, los estados de nodo, los
eventos y las aprobaciones de cada run. Además, los procesos pueden
interrumpirse (cierre de terminal, reinicio de la máquina), por lo que el motor
necesita reanudar sin repetir trabajo ya completado.

El producto es local-first y de usuario único. No hay servidor, cuentas ni
sincronización en el MVP.

## Decisión

Usar **SQLite local** en `.orchestrator/state/penfold.db`, accedido mediante
SQLAlchemy 2.0, con cuatro tablas:

- `runs`: cabecera del run, entradas/salidas/aprobación (como JSON), estado y
  bandera de cancelación. El "checkpoint" no es una columna separada: es el
  estado persistido entre `runs` y `node_states`.
- `node_states`: un registro por `(run_id, node_id)` con estado, iteración,
  timings, entrada/salida, errores e intentos.
- `events`: `RunEvent` con `seq` monótono por run; base del replay SSE y de la
  auditoría.
- `approvals`: solicitudes y decisiones humanas.

Detalle de columnas, índices y retención: [DATA_MODEL.md](../../../DATA_MODEL.md).

**Política de recuperación**:

- Los runs `running` que encuentre el servidor al arrancar se marcan `paused`.
- `POST /api/runs/{id}/resume` reconstruye el motor desde las filas persistidas
  (`prepare_resume()`): los nodos `succeeded` no se reejecutan, los nodos
  pendientes/interrumpidos vuelven a `pending` y la secuencia de eventos
  continúa.
- La cancelación (`POST /api/runs/{id}/cancel`) pone una bandera que el motor
  comprueba entre nodos; el nodo en curso pasa a `cancelled`.

**Por qué no la nube**: añadiría latencia, dependencia de red, cuentas, facturación
y un modelo de confianza incompatible con "los archivos y la historia están en
tu máquina". Ningún requisito del MVP lo justifica.

## Consecuencias

### Positivas

- Cero operaciones: SQLite viene con Python; no hay daemon ni contenedor.
- Transacciones ACID locales para estados y eventos; el archivo se puede
  copiar como parte del proyecto.
- El replay SSE sale de la tabla `events`, sin bus de mensajes externo.
- Los checkpoints permiten reanudar de forma determinista.

### Negativas

- Un único escritor: la concurrencia se limita con `execution.max_concurrency`
  y transacciones cortas; no apto para múltiples procesos simultáneos.
- La base de datos es local a una máquina: no hay sincronización entre equipos.
- El estado de reanudación se deriva de `node_states`: un cambio en la
  semántica de estados debe migrarse con cuidado entre versiones.

## Alternativas consideradas

1. **PostgreSQL/servidor externo**: rompe local-first y añade operaciones.
2. **Solo archivos JSON**: sin transacciones ni índices; costoso de consultar y
   propenso a corrupción al reanudar.
3. **DuckDB u otra base embebida**: no aporta ventajas frente a SQLite para
   escrituras transaccionales pequeñas.

## Retención

Los directorios `.orchestrator/state/`, `.orchestrator/runs/` y
`.orchestrator/artifacts/` se ignoran en Git. La política de retención
(configurable; por defecto 100 runs o 30 días) se describe en
[DATA_MODEL.md](../../../DATA_MODEL.md).
