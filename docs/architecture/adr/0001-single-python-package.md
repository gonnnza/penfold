# ADR-0001: Un único paquete Python `penfold` con submódulos internos

- Estado: propuesto
- Fecha: 2026
- Relacionado: [ADR-0002](0002-execution-engine-protocol.md)

## Contexto

Penfold tiene varias responsabilidades claras: CLI, servidor HTTP, motor de
ejecución, workflows, agentes, runtimes, configuración e integraciones. Cabría
la opción de publicar cada una como un paquete Python independiente con su
propio `pyproject.toml` y ciclo de versionado (un monorepo de librerías).

Sin embargo, el producto es una **aplicación local única**: la CLI, el servidor
y el motor se instalan y arrancan juntos, comparten modelos de dominio y se
versionan como un todo (0.1). No hay consumidores externos de estas librerías.

## Decisión

Usar **un único paquete Python distribuible** `penfold`, definido en
`pyproject.toml`, con submódulos internos:

```
src/penfold/
├── cli/           # Typer + Rich: init, doctor, start
├── server/        # FastAPI, rutas, SSE, autenticación por token
├── execution/     # ExecutionEngine, nodos, checkpoints, cancelación
├── workflows/     # modelos y validación de WorkflowDefinition
├── agents/        # modelos de AgentDefinition y registro
├── runtimes/      # MockRuntime, CommandRuntime, interfaz AgentRuntime
├── config/        # carga de config.yaml y .orchestrator/
└── integrations/  # punto de extensión futuro (sin producto concreto en 0.1)
```

El entry point es `penfold = penfold.cli.main:app`. No hay frontend web: la
interfaz es la TUI de terminal. El servidor
sirve el resultado. Es decir: **monorepo con dos apps** (`src/penfold` y
paquetes Python adicionales.

## Consecuencias

### Positivas

- Un solo `uv sync`, un solo `uv.lock`, una sola versión (`0.1.0`).
- Los modelos Pydantic se importan directamente entre capas sin conversiones
  entre paquetes ni dependencias circulares entre distribuciones.
- Los tests (pytest) ven todo el código fuente sin instalar paquetes herméticos.
- Refactorizar es más barato: mover código entre submódulos no cambia la API
  pública.

### Negativas

- Los submódulos no se pueden versionar ni publicar por separado. Si en el
  futuro `AgentRuntime` necesita ser consumido por terceros, habrá que extraer
  un paquete con su propio ADR.
- El límite entre capas debe mantenerse por convención y tests de arquitectura,
  no por dependencias declaradas en `pyproject.toml`.

## Alternativas consideradas

1. **Varios paquetes (`penfold-core`, `penfold-server`, `penfold-cli`, …)**:
   más aislamiento, pero sobrecoste de versionado, publicación y resolución de
   dependencias que el MVP no necesita.
2. **Un solo módulo sin submódulos**: más simple al inicio, pero mezcla
   responsabilidades y dificulta la extensión (nuevos nodos/runtimes).

## Cumplimiento

- No crear nuevos `pyproject.toml` fuera de la raíz.
- Las dependencias nuevas se añaden a la raíz; las de desarrollo al extra
  `dev`.
- Este ADR se revisaría si aparece un consumidor externo real de alguna capa.
