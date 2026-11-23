# skills.md — Catálogo de procedimientos de Penfold

> **Documento vivo.** Aquí se recogen las recetas repetibles ("skills") para
> trabajar en este repo. Cada vez que codeemos algo nuevo, añadimos una entrada
> o actualizamos una existente, y la registramos al final del archivo.
> Las reglas generales están en [`AGENTS.md`](AGENTS.md); este archivo es el
> **cómo** paso a paso.

## Cómo mantener este archivo

Formato de cada entrada:

```md
### nombre-de-la-skill

**Estado:** borrador | validado | obsoleto
**Cuándo usarla:** …
**Entrada:** qué necesitas tener/aclarar antes de empezar.
**Pasos:**
1. …
2. …
**Verificación:** comandos exactos que demuestran que funcionó.
**Trampas:** lo que ya nos bugueó al ejecutarla.
**Última práctica:** fecha y cambio por el que se tocó.
```

Índice (se rellena a medida que se añaden):

| Skill | Estado | Última práctica |
|---|---|---|
| [`verificacion-completa`](#verificacion-completa) | validado | 2026-11-23 |
| [`anadir-tipo-de-nodo`](#anadir-tipo-de-nodo) | validado | 2026-11-23 |
| [`anadir-runtime`](#anadir-runtime) | validado | 2026-11-23 |
| [`cambiar-contrato-http`](#cambiar-contrato-http) | validado | 2026-11-23 |
| [`anadir-agente-de-ejemplo`](#anadir-agente-de-ejemplo) | validado | 2026-11-23 |
| [`recompilar-ui`](#recompilar-ui) | validado | 2026-11-23 |
| [`depurar-un-run`](#depurar-un-run) | validado | 2026-11-23 |
| [`escribir-un-adr`](#escribir-un-adr) | validado | 2026-11-23 |
| [`anadir-endpoint-mvc`](#anadir-endpoint-mvc) | validado | 2026-11-23 |
| [`usar-dashboard-terminal`](#usar-dashboard-terminal) | validado | 2026-11-23 |

---

## verificacion-completa

**Estado:** validado
**Cuándo usarla:** antes de dar por terminado cualquier cambio; es el chequeo
mínimo obligatorio de `AGENTS.md` §6.

**Entrada:** ninguna.

**Pasos:**
1. Backend: `uv run ruff check .` → `uv run ruff format --check .` →
   `uv run pytest`.
2. Frontend (si toca `web/`): `cd web && pnpm test && pnpm build`.
3. E2E (si el cambio afecta al flujo de la UI): `cd web && pnpm test:e2e`.
4. Contrato: si el cambio toca modelos, confirma que
   `docs/development/API_CONTRACT.md` sigue siendo la fuente autoritativa.

**Verificación:** los comandos terminan sin errores. Si `pnpm build` falla con
un error de TypeScript, corrígelo antes de seguir.

**Trampas:** `ruff format` puede no estar habilitado como check en CI; usa
`uv run ruff format --check .` para detectar diffs sin modificar archivos.

**Última práctica:** 2026-11-23 — creación de la skill.

---

## anadir-tipo-de-nodo

**Estado:** validado
**Cuándo usarla:** cuando el grafo necesita un nuevo tipo de nodo (además de
`input`, `agent`, `command`, `condition`, `approval`, `output`).

**Entrada:** semántica clara: entradas, salidas, eventos y cómo se referencia su
salida (`$nodes.<id>.output`).

**Pasos:**
1. Define la forma YAML: añade el valor a `NodeType` y las claves de `config`
   en la tabla de nodos de `docs/development/API_CONTRACT.md`; documenta los
   campos en `WORKFLOW_SCHEMA.md`.
2. Registra las reglas de validación en `src/penfold/services/` (ids, campos
   obligatorios, referencias). Todo error lleva `path` y severidad.
3. Implementa el ejecutor en `src/penfold/services/`: resuelve `config.inputs`
   con mapeos, emite eventos antes/después, actualiza `NodeState`
   (`pending → ready → running → succeeded|failed`), respeta timeout, reintentos
   y cancelación.
4. Da de alta el tipo en la fábrica de nodos del motor.
5. Tests de mapeos, estados y eventos; ejemplo en
   `docs/user-guide/EXAMPLES.md`.

**Verificación:** `uv run pytest` + `uv run ruff check .`. El servidor no
debería necesitar cambios: el contrato HTTP usa la forma genérica de
`WorkflowNode`.

**Trampas:** no dependas de `position` en el ejecutor. Si el nodo produce
salida, documenta cómo se referencia desde `$nodes`.

**Última práctica:** 2026-11-23 — creación de la skill a partir de
`docs/development/EXTENDING.md` y `docs/CONTRIBUTING.md`.

---

## anadir-runtime

**Estado:** validado
**Cuándo usarla:** para conectar una nueva forma de obtener la salida de un nodo
`agent`.

**Entrada:** nombre del runtime, `command`/`args` declarados por el usuario y
contrato de salida JSON Schema.

**Pasos:**
1. Implementa `AgentRuntime` (`execute` / `validate` / `healthcheck`) en
   `src/penfold/services/runtimes/base.py` y regístralo en `registry.py` por
   `runtime.type`. Contrato estable: comprueba siempre el código antes de
   programar contra él (`RuntimeContext`, `RuntimeResult`).
2. `validate()`: comprueba `runtime.type`, `command`, `args` y `outputs`.
3. `healthcheck()`: rápido, sin efectos destructivos, mensaje claro si falta el
   ejecutable; un runtime no listo **no** debe bloquear el arranque.
4. `execute()`: respeta `timeout`, `retries`, `permissions` y redacción de
   secretos; usa **exactamente** `runtime.command` y `runtime.args` del agente,
   pasando los datos por el mecanismo que el runtime defina (stdin o posición
   concreta en `args`). Nunca inventes `--model`, `-p`, `--continue`, etc.
5. Salida validada contra `agent.outputs.schema`; si falla, nodo `failed`. Sin
   shell: `shlex.split`, lista de args, `cwd` relativo al repo.
6. Rechaza un agente cuyo `command` no esté en `permissions.allowed_commands`.
7. Tests: éxito, timeout, error de validación, secreto redactado y salud.

**Verificación:** `uv run pytest tests/test_runtimes.py` + `uv run ruff check .`.

**Trampas:** Penfold es orquestador neutral, **no** un wrapper de un CLI de IA.
No detectes flags automáticamente. El campo `simulated` del runtime se propaga
a `NodeState.simulated`.

**Última práctica:** 2026-11-23 — creación de la skill a partir de
`docs/development/EXTENDING.md`.

---

## cambiar-contrato-http

**Estado:** validado
**Cuándo usarla:** cada vez que cambie una entidad o un endpoint de la API.

**Entrada:** qué campo/endpoint cambia y por qué.

**Pasos:**
1. Edita **primero** `docs/development/API_CONTRACT.md` (fuente de verdad).
2. Actualiza los modelos Pydantic en
   `src/penfold/{workflows,agents,execution}/models.py` y los handlers en
   `src/penfold/views/app.py`.
3. Ajusta el cliente `web/src/api.ts` y los tipos `web/src/types.ts`.
4. Actualiza tests de API (`tests/test_api.py`) y de frontend
   (`web/src/api.test.ts`).
5. Un cambio de `schema_version` requiere discusión previa y ADR.

**Verificación:** `uv run pytest tests/test_api.py` y `cd web && pnpm build`.

**Trampas:** los nombres de entidades/campos deben coincidir en spec, contrato,
código y UI. Los errores de API van en inglés (`{"detail": "..."}`).

**Última práctica:** 2026-11-23 — creación de la skill.

---

## anadir-agente-de-ejemplo

**Estado:** validado
**Cuándo usarla:** al crear un agente reutilizable para los ejemplos/demo.

**Entrada:** responsabilidad del agente, rol, permisos y salida esperada.

**Pasos:**
1. Crea `examples/agents/<id>.yaml` con `schema_version: 1` y todos los campos
   del contrato: `role`, `instructions`, `runtime`, `permissions`, `inputs`,
   `outputs`, `timeout`, `retries`.
2. Usa `MockRuntime` con `mock.output` fijo para que la demo sea determinista.
3. Define `outputs.schema` con JSON Schema y `permissions.mode` acorde a su
   responsabilidad (`read_only`, `workspace_write`, `restricted`).
4. Añade su papel a la tabla de `docs/PROJECT_SPEC.md` y un caso en
   `docs/user-guide/EXAMPLES.md`.

**Verificación:** `uv run penfold workflow validate <id>` sobre un workflow que
lo referencie; `uv run pytest`.

**Trampas:** sin secretos en el YAML; los secretos van por variables de entorno.

**Última práctica:** 2026-11-23 — creación de la skill.

---

## recompilar-ui

**Estado:** validado
**Cuándo usarla:** después de cualquier cambio en `web/src/` o antes de probar
la UI desde el paquete instalado.

**Entrada:** ninguna.

**Pasos:**
1. `cd web && pnpm build` (ejecuta `tsc --noEmit && vite build`).
2. Sincroniza el build con la copia que sirve el servidor:
   `apps/server/static/` (ADR-0007). El wheel genera `penfold/static` desde
   ahí con `force-include`; no edites esa ruta a mano.
3. `uv run penfold start` y abre la URL que imprime; el token está en la
   terminal y en `.orchestrator/state/server.token`.

**Verificación:** la UI carga, `GET /api/health` responde y el workflow de
ejemplo se ve en el editor.

**Trampas:** cambiar solo `web/dist` no actualiza lo que sirve una instalación;
hay que copiarlo a `apps/server/static` y reconstruir el wheel. Para desarrollo
rápido, `pnpm dev` usa Vite directamente.

**Última práctica:** 2026-11-23 — creación de la skill.

---

## depurar-un-run

**Estado:** validado
**Cuándo usarla:** cuando un run falla, se queda colgado o no reanuda.

**Entrada:** `run_id`.

**Pasos:**
1. `uv run penfold inspect <run_id>` → detalle con `NodeState` y evento de error.
2. `uv run penfold logs <run_id>` → secuencia de eventos (`seq`, `type`, `level`,
   `node_id`, `message`).
3. `GET /api/runs/{id}/events?after=<seq>` para reconstruir el estado sin SSE.
4. Si está `paused`: revisa que los nodos `succeeded` no se repitan y llama a
   `POST /api/runs/{id}/resume`.
5. Si está `waiting_approval`: `POST /api/runs/{id}/approve` con la decisión.
6. Para cancelar: `POST /api/runs/{id}/cancel` (o `penfold cancel`).

**Verificación:** el run termina en `completed` o `failed` con un `error`
legible, y los eventos explican la transición.

**Trampas:** los eventos llevan `seq` monótono por run y se reproducen con
`after=<seq>`. Los runs `running` interrumpidos pasan a `paused` al arrancar el
servidor; eso es esperado, no un bug.

**Última práctica:** 2026-11-23 — creación de la skill.

---

## escribir-un-adr

**Estado:** validado
**Cuándo usarla:** cambios de paquetizado, motor, formato YAML, persistencia o
autenticación.

**Entrada:** decisión, alternativas consideradas y rationale.

**Pasos:**
1. Comprueba los ADR existentes en `docs/architecture/adr/` (hay 0001–0005) y
   toma el siguiente número consecutivo.
2. Copia el formato de los existentes: título, estado (`propuesto | aceptado |
   obsoleto`), contexto, decisión, consecuencias y alternativas.
3. Añade el enlace desde la tabla "Decisiones de diseño" de
   `docs/ARCHITECTURE.md`.

**Verificación:** el ADR está referenciado desde `docs/ARCHITECTURE.md` y el
número no se repite.

**Trampas:** los ADR existen físicamente; no los destruyas al reordenar la
documentación (parte de ella se reubicó en `docs/`).

**Última práctica:** 2026-11-23 — creación de la skill.

---

## anadir-endpoint-mvc

**Estado:** validado
**Cuándo usarla:** al añadir o modificar un endpoint HTTP, o cualquier regla de
negocio, bajo el patrón MVC de [ADR-0006](docs/architecture/adr/0006-mvc-layering.md).

**Entrada:** contrato del endpoint (método, ruta, request/response) y regla de
negocio que debe ejecutar.

**Pasos:**
1. **Model** (`src/penfold/models/`): declara la clase Pydantic del request y de
   la response. Solo declaración: campos, `Field`, validadores de clase. Nada de
   lógica ni de acceso a disco. Si necesitas `utcnow`, impórtalo de
   `penfold.utils`.
2. **Service** (`src/penfold/services/`): implementa la regla de negocio como
   función o método de un service existente (`manager.py`, `engine.py`,
   `validator.py`, stores…). Nunca importes FastAPI aquí.
3. **View** (`src/penfold/views/app.py`): añade el endpoint con `@app.*`, llama
   al service y devuelve `model_dump(mode="json")`. Sin reglas de negocio en el
   handler.
4. Si el cambio afecta al contrato, edita primero
   `docs/development/API_CONTRACT.md` (skill `cambiar-contrato-http`).
5. Ajusta `web/src/api.ts` y `web/src/types.ts` si la UI lo consume.
6. Tests: `tests/test_api.py` con `httpx` contra `create_app`.

**Verificación:** `uv run pytest tests/test_api.py` + `uv run ruff check .` +
`cd web && pnpm build` si tocó el cliente.

**Trampas:** dependencias permitidas solo `views → services → models → utils`.
Un model que importa services, o un view con lógica, rompe el patrón. Los 23
endpoints viven en `views/app.py`; la CLI es otro adaptador que llama a los
mismos services.

**Última práctica:** 2026-11-23 — refactor completo a MVC (33 tests pasan).

---

## usar-dashboard-terminal

**Estado:** validado
**Cuándo usarla:** para ejecutar y supervisar workflows desde la terminal, sin
arrancar el servidor ni abrir el navegador.

**Entrada:** proyecto inicializado (`penfold init`).

**Pasos:**
1. `uv run penfold tui`. Requiere `.orchestrator/` en el cwd o en un padre.
2. Menú principal: `[1]` tabla de workflows, `[2]` ejecutar, `[3]` historial de
   runs (detalle / cancelar / reanudar), `[4]` agentes, `[0]` salir.
3. Al ejecutar, se muestran las entradas declaradas con sus valores por defecto;
   acepta Enter para usarlos.
4. Durante la ejecución se actualizan en vivo el estado de los nodos y los
   eventos. Si aparece un nodo `approval`, elige `approve`, `reject`, `modify`
   (datos JSON) o `cancel`.
5. Al terminar se imprime el panel con estado y salidas.

**Verificación:** prueba rápida no interactiva:
`printf '1\n\n0\n' | uv run penfold tui` debe mostrar la tabla de workflows.

**Trampas:** los prompts corren en un hilo (`asyncio.to_thread`) para no
bloquear el event loop del motor. La TUI usa `manager.gate` (QueueApprovalGate),
así que las aprobaciones se resuelven con `manager.approve`, igual que la API.
No es un editor de grafos: para crear workflows usa la UI web o edita el YAML.

**Última práctica:** 2026-11-23 — smoke test de ejecución completa del workflow
`simple` desde la TUI.

---

## Registro de cambios

| Fecha | Cambio | Nota |
|---|---|---|
| 2026-11-23 | Creación inicial con 8 skills semilla derivadas del estado del repo. | Fases 0–6 hechas; Fase 7 en curso. |
| 2026-11-23 | Corrección de rutas a `docs/` y de enlaces internos del índice. | — |
| 2026-11-23 | Refactor a MVC; rutas de `skills.md` actualizadas y añadida `anadir-endpoint-mvc`. | ADR-0006 |
| 2026-11-23 | Añadida `usar-dashboard-terminal` tras implementar `penfold tui`. | — |
| 2026-11-23 | Actualizada `recompilar-ui`: una sola copia versionada del build (ADR-0007). | — |

> Si quieres convertir alguna de estas skills en una skill real de OpenCode,
> muévela a `.opencode/skills/<nombre>/SKILL.md` con frontmatter `name` y
> `description`. Este archivo seguirá siendo el índice legible del proyecto.
