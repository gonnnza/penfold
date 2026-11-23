# Primeros pasos con Penfold

> Esta guía describe el flujo objetivo de la demo del MVP 0.1. Algunas fases
> siguen en curso (ver [ROADMAP.md](../../ROADMAP.md)); si un paso no está
> disponible todavía, consulta el estado de cada fase.

## 1. Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node 20+
- [pnpm](https://pnpm.io/)

Penfold es local-first: no necesitas cuenta, conexión a Internet durante el uso
ni Docker. El servidor solo escucha en `127.0.0.1:8765`.

## 2. Instalar

Desde la raíz del repositorio de Penfold:

```bash
uv sync --extra dev
uv run penfold --help

cd web
pnpm install
pnpm build
cd ..
```

Después de esto, el binario `penfold` está disponible con `uv run penfold ...`.

## 3. Inicializar un repositorio de usuario

En el repositorio donde quieras trabajar (por ejemplo un proyecto propio):

```bash
uv run penfold init
uv run penfold doctor
```

`init` crea `.orchestrator/` con:

```
.orchestrator/
├── config.yaml
├── agents/
├── workflows/
├── state/penfold.db
├── runs/
└── artifacts/
```

`doctor` verifica que el entorno está listo y que no haya otro proceso usando
el puerto 8765.

Si vas a versionar tu proyecto, asegúrate de ignorar
`.orchestrator/state/`, `.orchestrator/runs/` y `.orchestrator/artifacts/`.
Sí se versionan `config.yaml`, `agents/` y `workflows/`.

## 4. Arrancar el servidor

```bash
uv run penfold start
```

La terminal muestra algo parecido a:

```
Penfold 0.1.0 — http://127.0.0.1:8765
Token local: <token>
```

Abre la URL en el navegador. La UI guarda el token en `localStorage`, de modo
que no tendrás que pegarlo de nuevo. El token también queda en
`.orchestrator/state/server.token` (permisos `0600`) y se reutiliza en futuros
arranques. Todas las peticiones usan la cabecera `X-Penfold-Token`; SSE usa
`?token=` porque `EventSource` no puede fijar cabeceras.

Comprobación rápida desde otra terminal:

```bash
curl http://127.0.0.1:8765/api/health
# {"status":"ok","version":"0.1.0"}
```

## 5. Crear tu primer workflow (Input + Agent + Output)

1. En la UI, pulsa **Nuevo workflow** y asígnale un id, por ejemplo `hello`.
2. Arrastra tres nodos al lienzo: **Input**, **Agent** y **Output**.
3. Conecta `Input → Agent → Output` arrastrando desde los puntos de conexión.
4. Configura cada nodo en el panel lateral:
   - **Input**: declara una entrada `request` de tipo `string`, obligatoria.
   - **Agent**: selecciona el agente `product-analyst` y mapea
     `request: $inputs.request`.
   - **Output**: en `config.inputs` mapea, por ejemplo,
     `summary: $nodes.analyst.output.summary` y elige `format: json`.
5. Pulsa **Guardar**.

Se habrá creado `.orchestrator/workflows/hello.yaml`. Ábrelo con un editor de
texto: verás `schema_version: 1`, tus nodos (con `position`), las aristas y los
mapeos. Puedes editarlo a mano y recargar la UI: el grafo se recupera igual.
El motor ignora `position`, así que mover nodos no cambia la ejecución.

## 6. Ejecutar con MockRuntime

1. Selecciona el workflow `hello` en la lista.
2. Introduce un valor para `request`, por ejemplo
   «Añade autenticación JWT».
3. Pulsa **Ejecutar**.

`MockRuntime` devuelve una salida determinista declarada en `mock.output` del
agente. Verás los nodos cambiar de `pending` a `ready`, `running` y
`succeeded`, y los eventos llegando por SSE. Los estados se guardan en SQLite.

También puedes crear el run por API:

```bash
curl -X POST http://127.0.0.1:8765/api/runs \
  -H "X-Penfold-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"workflow_id":"hello","inputs":{"request":"Añade autenticación JWT"}}'
```

La respuesta es un `RunDetail` con un `id`. Para seguirlo:

```bash
curl -N "http://127.0.0.1:8765/api/runs/<id>/stream?token=<token>"
```

## 7. Ver estados, aprobar y recuperar

- El panel de ejecución muestra el estado de cada nodo y el historial de
  eventos. Si la conexión SSE se corta, la UI reconecta con `after=<seq>` y
  recupera los eventos perdidos.
- Si el workflow incluye un nodo `approval`, el run pasa a
  `waiting_approval`. Revisa el contenido y elige **Aprobar**, **Rechazar** o
  **Modificar**. El run continúa o falla según la decisión.
- Puedes cancelar un run en curso; el motor se detiene entre nodos y marca el
  nodo en curso como `cancelled`.
- Cierra la UI y vuelve a abrirla: el historial de runs y su detalle se leen
  desde `.orchestrator/state/penfold.db`. Si el servidor se reinició mientras
  un run estaba `running`, este aparece como `paused`; usa **Reanudar** para
  continuar desde el checkpoint sin repetir nodos exitosos.

## 8. Siguiente paso

Prueba los flujos completos descritos en [EXAMPLES.md](EXAMPLES.md),
en particular el caso de desarrollo JWT. Para entender el formato del YAML y
las reglas de validación, consulta [WORKFLOW_SCHEMA.md](../../WORKFLOW_SCHEMA.md).
