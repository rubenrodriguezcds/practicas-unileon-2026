# Issue #7 — Gestión de proyectos y documentos adjuntos

Rama: `feature/gestion-proyectos-#7` (sale de `main`, con #4 y #5). La #6 (usuarios) va en paralelo
en otra rama: esta issue usa la migración `004` (la `003` es de la #6) y en los ficheros comunes
solo añade líneas.

Decisiones y su porqué: `GUIA_ISSUE_7.md`, apartado 2.

## Qué pide la issue

1. Tabla `proyectos`: id secuencial, nombre, tipo, descripción (texto).
2. Tabla `documentos`: id secuencial, id del proyecto (FK), nombre del archivo, contenido (blob).
3. Menú para gestionar proyectos: crear, borrar y editar (nombre, tipo y descripción, y añadir y borrar documentos; cambiado el 12-11, D38).
4. Borrar un proyecto borra todos sus documentos.

## Criterios de aceptación

- Solo el administrador: todos los endpoints responden 401 sin sesión y 403 si no es admin; la
  entrada «Proyectos» del menú solo la ve el admin y `/proyectos` redirige a `/` si no lo es.
- Crear proyecto con nombre (obligatorio, único sin distinguir mayúsculas), tipo y descripción
  (opcionales, texto libre). Nombre, tipo y descripción se editan desde el detalle (`PUT`, 409 si el nombre choca).
- Listado de proyectos (por nombre) con su número de documentos.
- Detalle de un proyecto: sus datos y la tabla de documentos (nombre, tamaño, Ver, Descargar,
  Borrar) y una zona para arrastrar y soltar varios archivos.
- Subida: un archivo por petición; lista de tipos permitidos (415 si no); máx. 50 MB (413);
  nombre único en el proyecto con extensión y sin distinguir mayúsculas (409); vacío → 422.
- Ver en el navegador solo PDF, imágenes y texto; lo demás se descarga. Siempre `nosniff` y
  `Content-Security-Policy: sandbox` salvo en PDF (el visor de Chrome se queda en blanco con ella).
- Borrar proyecto o documento con una ventana de aviso propia (modal). El de proyecto dice cuántos
  documentos se borrarán. La bbdd borra los documentos sola (`ON DELETE CASCADE`).
- Sin `docker compose down -v`: migración `004` aplicada al arrancar.
- `pytest`, `ruff check`, `npm test`, `npm run lint`, `npm run build` en verde y prueba en Chrome.

## Diseño

### bbdd: `api/migrations/004_proyectos.sql`

```sql
CREATE TABLE IF NOT EXISTS proyectos (
  id          SERIAL       PRIMARY KEY,
  nombre      VARCHAR(100) NOT NULL,
  tipo        VARCHAR(100),
  descripcion TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS proyectos_nombre_unico ON proyectos (lower(nombre));

CREATE TABLE IF NOT EXISTS documentos (
  id          SERIAL       PRIMARY KEY,
  proyecto_id INTEGER      NOT NULL REFERENCES proyectos (id) ON DELETE CASCADE,
  nombre      VARCHAR(255) NOT NULL,
  contenido   BYTEA        NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS documentos_nombre_unico ON documentos (proyecto_id, lower(nombre));
```

- Unicidad con índices sobre `lower(...)`: la bbdd garantiza «sin distinguir mayúsculas» y evita
  carreras entre dos peticiones (`UniqueViolation` → 409), igual que roles.
- El índice único `(proyecto_id, lower(nombre))` sirve también para buscar documentos por proyecto.
- Sin columna de tipo de archivo: se deduce de la extensión del nombre.

### Tipos de archivo (`api/app/documentos.py`)

Un único sitio con la lista de extensiones permitidas, su `Content-Type` y si se pueden ver:

| Extensiones | Content-Type | Ver |
|---|---|---|
| `.pdf` | `application/pdf` | sí |
| `.png .jpg .jpeg .gif .webp` | `image/…` | sí |
| `.txt .md .csv` | `text/plain; charset=utf-8` | sí |
| `.doc .docx .xls .xlsx .ppt .pptx .odt .ods .odp` | los oficiales de cada formato | no |

Funciones: `tipo_de(nombre) -> TipoArchivo | None`, `limpiar_nombre(nombre) -> str` (quita rutas
`C:\…\` o `…/`, espacios a los lados y caracteres de control; vacío o > 255 → `ValueError`) y
`content_disposition(nombre, inline)` (cabecera con `filename*=UTF-8''…` para acentos).

### Límite de tamaño

- `DOCUMENTO_MAX_MB` (defecto 50) en `config.py`, `.env.example` y README.
- **Antes de leer el cuerpo**: un middleware mira `Content-Length` en `POST /api/proyectos/{id}/documentos`;
  si pasa del máximo (+1 MB de margen para las cabeceras del multipart) → 413 sin leer nada. Sin
  `Content-Length` → 411. Así un fichero de 2 GB no llega a escribirse en el disco temporal.
- **Después**, el endpoint comprueba el tamaño real del fichero (> máximo → 413).
- La descarga carga el documento entero en memoria (máx. 50 MB): aceptable con un solo admin.
  `shortcut:` comentado en el código para pasar a streaming si sube el límite.

### API: `api/app/routers/proyectos.py` (router con `require_admin`)

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/api/proyectos` | 200 `[{id, nombre, tipo, descripcion, num_documentos}]` por nombre |
| POST | `/api/proyectos` `{nombre, tipo, descripcion}` | 201 proyecto · 409 nombre repetido · 422 |
| GET | `/api/proyectos/{id}` | 200 proyecto + `documentos: [{id, nombre, tamano}]` (sin contenido) · 404 |
| DELETE | `/api/proyectos/{id}` | 204 · 404 |
| POST | `/api/proyectos/{id}/documentos` (multipart, campo `archivo`) | 201 `{id, nombre, tamano}` · 404 · 409 · 411 · 413 · 415 · 422 |
| GET | `/api/documentos/{id}` (`?ver=1` para abrir en el navegador) | 200 bytes · 404 |
| DELETE | `/api/documentos/{id}` | 204 · 404 |

En todos: 401 sin sesión · 403 si no es admin · 503 bbdd caída. Los de `/api/documentos` van en
un segundo router del mismo fichero, también con `require_admin`.

- Nombre y tipo: sin espacios a los lados, nombre obligatorio (1–100), tipo opcional (≤ 100, vacío
  → NULL), descripción opcional (≤ 1000, vacía → NULL), como `RolIn`.
- Descarga: `Content-Type` del tipo; `Content-Disposition: inline` solo si `ver=1` **y** el tipo se
  puede ver, si no `attachment`; siempre `X-Content-Type-Options: nosniff`,
  `Content-Security-Policy: sandbox` (salvo PDF, ver arriba) y `Cache-Control: private, no-store`.
- Mensajes: «Ya existe un proyecto con ese nombre», «Ya existe un documento con ese nombre en el
  proyecto», «El proyecto no existe», «El documento no existe», «Tipo de archivo no permitido»,
  «El archivo pasa de 50 MB», «El archivo está vacío».
- Dependencia nueva: `python-multipart` (FastAPI la necesita para `UploadFile`).

### bbdd en código: `api/app/db.py`, sección «Proyectos (issue #7)»

`list_projects`, `create_project` (`NombreDuplicado` si se repite, la clase de roles),
`get_project` (con documentos y `octet_length(contenido)` como tamaño, sin cargar el contenido),
`delete_project` (devuelve si existía), `add_document` (`NombreDuplicado` si se repite; `None` si
el proyecto no existe), `get_document` (`nombre`, `contenido`) y `delete_document`.

### Frontend

- `api/client.ts`: tipos `Proyecto`, `ProyectoDetalle`, `Documento`; `listProjects`,
  `createProject`, `getProject`, `deleteProject`, `uploadDocument(proyectoId, file)`,
  `deleteDocument`, `documentUrl(id, ver)`. `request()` no pone `Content-Type: application/json`
  cuando el cuerpo es `FormData` (el navegador pone el suyo con el separador).
- `components/ConfirmDialog.tsx` (nuevo, reutilizable): modal con `<dialog>` nativo (foco atrapado y
  Escape gratis); título, mensaje, «Cancelar» y botón de confirmar en rojo.
- `components/DropZone.tsx` (nuevo): zona de arrastrar y soltar + botón que abre el selector
  (`<input type="file" multiple>`); entrega la lista de archivos al padre. Accesible con teclado.
- `pages/Proyectos.tsx` (nuevo, `/proyectos`): formulario «Nuevo proyecto», tabla (nombre → enlace
  al detalle, tipo, nº de documentos, «Borrar» con modal que dice cuántos documentos se borran).
- `pages/ProyectoDetalle.tsx` (nuevo, `/proyectos/:id`): datos del proyecto, DropZone y tabla de
  documentos (nombre, tamaño legible, «Ver» si el tipo se puede ver, «Descargar», «Borrar» con
  modal). Al soltar archivos sube uno a uno y muestra el estado de cada uno (subiendo, subido o el
  mensaje de error de la API); si pasa de 50 MB lo avisa sin subirlo. Tras subir o borrar, vuelve
  a pedir el detalle.
- «Ver» = enlace `target="_blank"` a `documentUrl(id, true)`; «Descargar» = enlace normal (sin `download`: la API manda `attachment` y, sin sesión, redirige al login; D39).
  Qué tipos se pueden ver lo dice la API (`visible` en cada documento del detalle), para no
  duplicar la lista en el frontend.
- `components/Layout.tsx`: entrada `{ to: '/proyectos', texto: 'Proyectos', soloAdmin: true }`.
- `App.tsx`: rutas `/proyectos` y `/proyectos/:id` dentro del `Layout`, redirigiendo si no es admin.

Por tanto `documentos` del detalle es `[{id, nombre, tamano, visible}]`.

## Tests (TDD: cada pieza empieza por su test)

**pytest** (FakeDB ampliada con proyectos y documentos, mismas reglas que la bbdd: únicos sin
mayúsculas y cascada):

- 401 y 403 en todos los endpoints de proyectos y documentos.
- Crear, listar (orden y `num_documentos`), detalle, borrar; nombre repetido con otras mayúsculas
  → 409; validaciones 422.
- Subir: correcto (201, tamaño), tipo no permitido (`.html`, `.svg`, `.exe`) → 415, vacío → 422,
  repetido con otras mayúsculas → 409, mismo nombre con otra extensión → 201, proyecto inexistente
  → 404, > máximo → 413 (con `DOCUMENTO_MAX_MB` pequeño en el test), `Content-Length` excesivo → 413
  sin leer el cuerpo, nombre con ruta → se guarda solo el nombre.
- Descargar: contenido idéntico, `attachment` por defecto, `inline` con `ver=1` en PDF, `attachment`
  con `ver=1` en `.docx`, `nosniff` siempre y `sandbox` en todo salvo PDF, nombre con acentos.
- Borrar proyecto borra sus documentos; borrar documento.
- `documentos.py`: tipos, limpiar nombre, Content-Disposition.
- Migración `004` idempotente; config `DOCUMENTO_MAX_MB`.

**Vitest**:

- «Proyectos» en el menú solo para admin; `/proyectos` redirige si no.
- Crear proyecto (y error 409 visible); borrar con modal que dice el nº de documentos; cancelar no borra.
- Detalle: lista documentos; «Ver» solo en los visibles; soltar varios archivos sube cada uno y
  muestra su estado; uno de > 50 MB se avisa sin subir; borrar documento con modal.
- `ConfirmDialog` y `DropZone` por separado; `uploadDocument` manda `FormData` sin `Content-Type` JSON.

## Fuera de alcance

Asignar usuarios a proyectos, permisos por rol, tipo como lista
fija, vista previa de documentos dentro de la app, streaming de descargas. Apuntados en la guía.
