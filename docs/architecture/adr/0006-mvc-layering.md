# ADR-0006: Arquitectura MVC — Model / Service / View

- Estado: aceptado
- Fecha: 2026-11-23
- Relacionado: [ADR-0001](0001-single-python-package.md),
  [ADR-0002](0002-execution-engine-protocol.md)

## Contexto

El prototipo 0.1 organizaba el código por dominio (`workflows/`, `agents/`,
`execution/`, `server/`, `runtimes/`). Cada paquete mezclaba modelos Pydantic,
lógica de negocio y, en el caso de `server/`, endpoints HTTP. Esa disposición
dificultaba responder preguntas básicas como «¿dónde va esta regla de negocio?»
y permitía que un modelo acabara con comportamiento o un endpoint con lógica.

Se pide adoptar explícitamente el patrón MVC con una definición estricta de
cada rol.

## Decisión

Reorganizar `src/penfold/` en tres capas con dependencia unidireccional
`views → services → models → utils`:

1. **Model** (`src/penfold/models/`): **solo declaración de clases**. Pydantic
   `BaseModel`, enums (`StrEnum`) y alias de tipos. Sin lógica de negocio, sin
   acceso a disco y sin FastAPI. Los validadores de campo siguen siendo parte
   de la declaración de la clase. Módulos: `workflow.py`, `agent.py`,
   `execution.py`, `config.py`, `runtime.py`.

2. **Service** (`src/penfold/services/`): **toda la lógica de negocio**. Motor
   de ejecución, gestor de runs, validación de grafos, repositorio SQLAlchemy,
   stores YAML, plantillas, aprobaciones, contexto, bus de eventos y los
   runtimes (`services/runtimes/`). No expone endpoints HTTP.

3. **View** (`src/penfold/views/`): **abre los endpoints**. FastAPI, rutas REST,
   SSE, archivos estáticos y middleware de token. Solo transporte: delega en
   services y serializa models con `model_dump()`.

La CLI (`src/penfold/cli/`) se considera otro adaptador de entrada, equivalente
a la view: invoca services directamente y no implementa reglas de negocio.
`config/paths.py` e `integrations/` son infraestructura. `utils.py` alberga
utilidades puras (p. ej. `utcnow`) para que models no tengan que importar
services para construir sus valores por defecto.

Se actualizan las rutas de importación en código, tests y documentación. No se
mantienen shims de compatibilidad: el proyecto es un MVP sin consumidores
externos y los 33 tests actúan como red de seguridad.

## Consecuencias

### Positivas

- Regla simple y verificable: «si tiene comportamiento, va en services; si
  declara datos, va en models; si es un endpoint, va en views».
- El motor sigue siendo independiente de FastAPI y de la UI (ADR-0002).
- Un modelo nuevo no puede traer efectos secundarios por accidente.

### Negativas

- Cambio de rutas de importación en todo el código y los tests.
- Los modelos quedan anémicos: las validaciones que dependen de varios campos
  siguen viviendo en los validadores Pydantic por pragmatismo, no en services.

## Alternativas consideradas

- **Mantener el diseño por dominio**: rechazada; es lo que se quiere corregir.
- **MVC con modelos activos (lógica dentro del modelo)**: rechazada; mezclaría
  persistencia y reglas de negocio con el contrato de datos compartido por CLI,
  motor y API.
