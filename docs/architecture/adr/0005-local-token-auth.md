# ADR-0005: Token local, SSE por query param y binding a localhost

- Estado: propuesto
- Fecha: 2026
- Relacionado: [ADR-0004](0004-sqlite-local-persistence.md)

## Contexto

El servidor FastAPI expone endpoints que crean runs, ejecutan comandos y
modifican archivos del repositorio. Aunque solo escucha en local, conviene
evitar que cualquier página web visitada por el usuario pueda hacer peticiones
al servicio (CSRF en localhost) o que un proceso local accidentalmente lo use.

Además, la UI consume eventos con `EventSource`, que **no permite fijar
cabeceras HTTP**; solo puede enviar parámetros en la query string.

## Decisión

1. **Binding a localhost**: uvicorn escucha en `127.0.0.1:8765`. No se expone a
   `0.0.0.0` ni se ofrece opción para hacerlo en el MVP.

2. **Token local**: al arrancar `penfold start`, el servidor genera un token y
   lo **imprime en la terminal** junto con la URL. Todos los endpoints `/api/*`
   salvo `/api/health` exigen la cabecera `X-Penfold-Token: <token>`.

3. **SSE por query param**: `GET /api/runs/{id}/stream?after=<seq>&token=<token>`
   acepta el token en la query porque `EventSource` no puede enviar la
   cabecera. Es la única excepción y no se usa en otros endpoints.

4. **Cliente**: no hay navegador; quien consuma la API (scripts, `curl`) envía
   el token en la cabecera `X-Penfold-Token`. La TUI y la CLI no usan HTTP.
   El token se conserva en `.orchestrator/state/server.token` con permisos
   `0600` para reutilizarlo entre arranques; no se escribe en YAML, SQLite,
   logs ni eventos.

5. **Sin usuarios**: no hay cuentas, roles ni sesiones. El token protege el
   servicio, pero cualquiera con acceso a la terminal tiene acceso completo.

Contrato detallado: [API_CONTRACT.md](../../development/API_CONTRACT.md).

## Consecuencias

### Positivas

- Configuración mínima: no hay login; basta enviar el token impreso en la
  terminal al arrancar.
- Mitiga peticiones cross-site accidentales a localhost: un sitio externo no
  conoce el token y no puede fijar la cabecera.
- `EventSource` funciona sin un polyfill que añada cabeceras.

### Negativas

- El token en la query puede acabar en logs de proxy o en el historial si se
  copia la URL. Se mitiga no registrando query strings en logs.
- No es autenticación multicliente ni sustituye a TLS: el tráfico va por loopback.

## Alternativas consideradas

1. **Cookie HttpOnly + SameSite**: encaja con cabeceras, pero `EventSource`
   enviaría la cookie y complicaría el arranque desde terminal; además el flujo
   de "token impreso" es más explícito para un usuario local.
2. **Sin autenticación**: más simple, pero cualquier página web podría
   interactuar con el servicio local.
3. **OAuth/cuentas**: desproporcionado para una herramienta de usuario único y
   sin nube.

## Medidas complementarias

- Redacción de secretos en logs y eventos ([SECURITY.md](../../../SECURITY.md)).
- El token **no** se regenera en cada arranque: se lee de
  `.orchestrator/state/server.token` y solo se genera uno nuevo si el archivo
  no existe. Si se sospecha exposición, borrar ese archivo y reiniciar.
- `/api/health` no lleva token para permitir comprobaciones simples, pero no
  expone información sensible: solo `{status, version}`.
