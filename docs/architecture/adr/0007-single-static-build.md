# ADR-0007: Una sola copia versionada del build del frontend

- Estado: aceptado
- Fecha: 2026-11-23
- Relacionado: [ADR-0001](0001-single-python-package.md)

## Contexto

El build de la UI se guardaba en tres rutas: `web/dist/` (generada e
ignorada por Git), `apps/server/static/` y `src/penfold/static/`. Las dos
últimas estaban versionadas y contenían los mismos archivos, con el riesgo de
que una quedara desactualizada. Además, `src/penfold/static/` se empaquetaba
directamente en el wheel porque Hatchling incluye todo `src/penfold`.

El servidor resuelve el directorio del frontend en
`ProjectPaths.static_dir`: primero la copia junto al paquete (`penfold/static`
dentro del wheel) y luego las copias del monorepo. Por tanto, borrar la copia
del árbol de fuentes sin más dejaría la UI fuera del paquete instalado.

## Decisión

1. `apps/server/static/` es la **única copia versionada** del build. Ya no se
   mantiene `src/penfold/static/` en el repositorio.
2. Hatchling genera `penfold/static` dentro del wheel desde
   `apps/server/static` mediante `force-include` en `pyproject.toml`.
3. `ProjectPaths.static_dir` conserva su orden de búsqueda: en una instalación
   encuentra la copia embebida en el wheel; trabajando desde el monorepo cae a
   `apps/server/static`. Si no hay ninguna copia, `views/app.py` sirve el
   mensaje de "frontend aún no compilado".

## Consecuencias

### Positivas

- Un solo `index.html` y un solo `assets/` que sincronizar tras `pnpm build`.
- El paquete instalado sigue sirviendo la UI sin depender del monorepo.
- No cambia ninguna ruta HTTP ni la lógica de `views/app.py`.

### Negativas

- La copia del wheel se genera en tiempo de build: quien construya el paquete
  debe tener `apps/server/static` actualizado.
- Hay que verificar el contenido del wheel tras cambiar la configuración de
  Hatchling.

## Alternativas consideradas

- **Eliminar la UI web y servir solo `penfold tui`**: rechazada; la UI web
  sigue siendo la interfaz principal y la TUI es complementaria.
- **Leer los archivos directamente desde `web/dist` en producción**:
  rechazada; `web/dist` está ignorado por Git y no existe en una instalación.
