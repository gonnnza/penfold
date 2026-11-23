# Seguridad de Penfold

Penfold es una herramienta local de usuario único. Su modelo de seguridad no
busca aislar procesos hostiles, sino evitar accidentes y exponer lo mínimo
imprescindible en la máquina del desarrollador.

## Superficie de exposición

- **Localhost por defecto**: el servidor escucha en `127.0.0.1:8765`. Nunca se
  enlaza a `0.0.0.0` en la configuración del MVP. No hay configuración de
  "exponer a la red".
- **Token local**: todos los endpoints `/api/*` salvo `/api/health` requieren
  la cabecera `X-Penfold-Token`. SSE no puede fijar cabeceras con `EventSource`,
  por lo que acepta `?token=<token>` como alternativa
  ([ADR-0005](docs/architecture/adr/0005-local-token-auth.md)).
- El token se **muestra en la terminal** al arrancar `penfold start` y se guarda
  en `.orchestrator/state/server.token` (`0600`). La TUI y la CLI no necesitan
  token: hablan directamente con los services. Quien tenga acceso a la terminal
  puede usar el servicio: no hay distinción de usuarios.

> No pegues el token en scripts compartidos ni en terminals remotas. El token
> se guarda en `.orchestrator/state/server.token` con permisos `0600` y se
> reutiliza entre arranques. Para rotarlo, elimina ese archivo antes de volver a
> ejecutar `penfold start`.

## Secretos

- **Nunca** guardar claves API, tokens de proveedor ni contraseñas en
  `.orchestrator/config.yaml`, `agents/*.yaml`, `workflows/*.yaml` ni en el
  código.
- Los secretos se leen de **variables de entorno**. Las definiciones de agentes
  pueden referenciar el *nombre* de la variable (por ejemplo
  `env: PENFOLD_MY_PROVIDER_KEY`), nunca su valor.
- Si un comando necesita un secreto, se inyecta en el entorno del proceso
  hijo por el runtime; el valor no se escribe en logs ni en el checkpoint.
- `GET /api/config` devuelve solo configuración no sensible (proyecto, defaults
  y límites de ejecución). Nunca secretos.

## Redacción de logs y eventos

- Los mensajes y `data` de `RunEvent` se **redactan** antes de persistirse:
  patrones de tokens (p. ej. `sk-...`, `Bearer ...`), variables declaradas como
  secretas y rutas de archivos sensibles se sustituyen por `[REDACTED]`.
- Los errores de subprocess se truncan y redactan antes de guardarse en
  `NodeState.error` / `runs.error`.
- La UI nunca muestra el token en el historial de eventos; el token viaja solo
  en la cabecera/query de la petición.
- No se registran prompts completos si contienen secretos; se aplica la misma
  redacción que a los eventos.

## Validación de paths

Todas las rutas que entran por la API se validan:

- `GET /api/artifacts/{run_id}/{name}` solo puede leer dentro de
  `.orchestrator/artifacts/<run_id>/`.
- Se rechazan `..`, separadores de ruta, rutas absolutas, bytes nulos y nombres
  vacíos.
- El `cwd` de un nodo `command` es **relativo** al repositorio y se resuelve
  contra la raíz del proyecto; no puede escapar con `../`.
- `read_paths` / `write_paths` de un agente se normalizan y restringen al
  workspace; una ruta fuera del workspace es error de validación.

## Comandos sin shell

`CommandRuntime` utiliza `shlex.split(command)` y ejecuta la lista de
argumentos resultante con el proceso directamente (`shell=False`).

- No hay expansión de `$VAR`, comodines ni tuberías (`|`, `;`, `&&`, backticks).
- Los argumentos que provienen de mapeos se pasan como datos, no se concatenan
  en una cadena interpretada.
- `allowed_commands` de un agente limita qué ejecutables puede usar el nodo
  `command`; los comandos no autorizados se rechazan antes de ejecutarse.
- `cwd`, `timeout`, `retries` y el número de procesos concurrentes están
  acotados por la configuración del servidor.

## Timeouts, reintentos y concurrencia

- `AgentDefinition.timeout` / `retries` y sus equivalentes por nodo limitan el
  tiempo y los intentos. Los reintentos son con backoff y nunca repiten un nodo
  ya `succeeded` al reanudar.
- `execution.default_timeout_seconds`, `execution.max_retries` y
  `execution.max_concurrency` en `config.yaml` actúan como valores por defecto
  y topes.
- `execution.max_iterations` limita las iteraciones de un run (por defecto 3),
  evitando bucles infinitos aunque el autor del workflow olvide
  `max_iterations` en la arista.
- La concurrencia se controla en el motor; no hay ejecución ilimitada de
  comandos en paralelo.

## Modos de permiso (NO es un sandbox)

`AgentDefinition.permissions.mode`:

| Modo | Significado |
|---|---|
| `read_only` | El agente solo consume datos; no se le concede escritura. |
| `workspace_write` | Puede proponer/escribir cambios dentro del workspace, limitado a `write_paths`. |
| `restricted` | Solo puede usar `read_paths` y `allowed_commands` declarados. |

**Advertencia importante**: estos modos son metadatos que el motor respeta al
construir contextos y decidir pasos. **No son un sandbox del sistema
operativo**. Un `CommandRuntime`, o un agente que devuelva texto que luego se
aplica al repo, se ejecuta con los permisos del usuario que lanzó Penfold. No
ejecutes Penfold con un usuario privilegiado ni en repositorios que no puedas
perder. El aislamiento con worktrees se estudia como evolución futura, pero
tampoco sería un sandbox (ver [ARCHITECTURE.md](ARCHITECTURE.md)).

## Autorizaciones

- El nodo `approval` fuerza una decisión humana: `approve`, `reject` o `modify`.
  El run permanece `waiting_approval` hasta que se envía
  `POST /api/runs/{id}/approve`.
- Los runs con aprobación pendiente no se cancelan ni se purgan
  automáticamente.
- La decisión, la nota, el momento y el revisor local quedan registrados en la
  tabla `approvals` ([DATA_MODEL.md](DATA_MODEL.md)).

## Auditoría

- Cada transición importante genera un `RunEvent` persistido con `seq`, `type`,
  `level`, `node_id`, `message`, `data` y `timestamp`.
- Los eventos permiten reconstruir qué pasó, en qué orden y con qué nodo; se
  consultan con `GET /api/runs/{id}/events?after=<seq>` y por SSE.
- El historial se conserva según la política de retención de
  [DATA_MODEL.md](DATA_MODEL.md). Los eventos redactados son la fuente de
  auditoría; no sustituyen a las trazas del sistema operativo.

## Alcance y limitaciones de seguridad del MVP

Incluido: localhost, token local, secretos por entorno, redacción, paths
validados, sin shell, timeouts/reintentos/concurrencia acotados, aprobaciones y
auditoría.

No incluido: autenticación de usuarios, TLS en el propio servidor, sandbox,
control de acceso por rol, cifrado de la base de datos, firma de artefactos ni
protección frente a un atacante con acceso local a la máquina.
