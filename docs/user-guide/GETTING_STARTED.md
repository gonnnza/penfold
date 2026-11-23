# Primeros pasos con Penfold

> Esta guía describe el flujo objetivo de la demo del MVP 0.1. Algunas fases
> siguen en curso (ver [ROADMAP.md](../../ROADMAP.md)); si un paso no está
> disponible todavía, consulta el estado de cada fase.

## 1. Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

Penfold es local-first: no necesitas cuenta, conexión a Internet durante el uso
ni Docker. El servidor solo escucha en `127.0.0.1:8765`.

## 2. Instalar

Para tener el comando `penfold` disponible en **cualquier carpeta**, instálalo
como herramienta con uv:

```bash
uv tool install git+https://github.com/gonnnza/penfold.git
# o desde un checkout local: uv tool install /ruta/a/penfold
penfold --version
```

Si prefieres no instalarlo, desde la raíz del repositorio:

```bash
uv sync --extra dev
uv run penfold --help
```

En ese caso usa `uv run penfold ...` en lugar de `penfold ...`.

## 3. Inicializar un repositorio de usuario

En el repositorio donde quieras trabajar (por ejemplo `/electrolux`):

```bash
cd /electrolux
penfold init
penfold doctor
```

No hace falta estar en el repo de Penfold. Los comandos buscan `.orchestrator/`
hacia arriba desde el directorio actual. Para apuntar a otro proyecto desde
cualquier sitio:

```bash
penfold --project /electrolux workflow list
penfold --project /electrolux tui
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

## 4. Abrir la interfaz de terminal

```bash
uv run penfold tui
```

La TUI lista workflows y agentes, lanza ejecuciones y muestra los estados de
los nodos y los eventos en vivo. Habla directamente con los services: no
necesita servidor HTTP ni token.

Si prefieres la API, `uv run penfold start` arranca el servidor en
`127.0.0.1:8765` e imprime el token (también guardado en
`.orchestrator/state/server.token` con permisos `0600`). Las peticiones usan
`X-Penfold-Token` y SSE usa `?token=`. Comprueba el servicio con
`curl http://127.0.0.1:8765/api/health`.

## 5. Crear tu primer workflow (Input + Agent + Output)

Crea `.orchestrator/workflows/hello.yaml` con un nodo `input`, un `agent` y un
`output`, conectados por aristas:

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
    config: {}
  - id: analyst
    type: agent
    agent: product-analyst
    config:
      inputs:
        request: $inputs.request
  - id: end
    type: output
    config:
      format: json
      inputs:
        summary: $nodes.analyst.output.summary
edges:
  - { id: e1, source: start, target: analyst }
  - { id: e2, source: analyst, target: end }
```

El campo `position` es opcional y el motor lo ignora. Valida el archivo con
`uv run penfold workflow validate hello`.

## 6. Ejecutar con MockRuntime

En la TUI elige `[2] Ejecutar`, escribe `hello` e introduce un valor para
`request`, por ejemplo «Añade autenticación JWT». Alternativamente:

```bash
uv run penfold run hello -i "request=Añade autenticación JWT" --watch
```

`MockRuntime` devuelve una salida determinista declarada en `mock.output`.
Verás los nodos pasar de `pending` a `ready`, `running` y `succeeded`, con sus
eventos en vivo. Los estados se guardan en SQLite.

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

- La TUI muestra el estado de cada nodo y el historial de eventos.
- Si el workflow incluye un nodo `approval`, el run pasa a `waiting_approval`:
  elige `approve`, `reject`, `modify` o `cancel` desde la propia TUI.
- Puedes cancelar un run en curso; el motor se detiene entre nodos.
- Cierra la TUI y vuelve a abrirla: el historial de runs y su detalle se leen
  desde `.orchestrator/state/penfold.db`. Si el servidor se reinició mientras
  un run estaba `running`, aparece como `paused`; usa `penfold resume <id>` o
  la opción `[3] Reanudar` de la TUI.

## 8. Siguiente paso

Prueba los flujos completos descritos en [EXAMPLES.md](EXAMPLES.md),
en particular el caso de desarrollo JWT. Para entender el formato del YAML y
las reglas de validación, consulta [WORKFLOW_SCHEMA.md](../../WORKFLOW_SCHEMA.md).
