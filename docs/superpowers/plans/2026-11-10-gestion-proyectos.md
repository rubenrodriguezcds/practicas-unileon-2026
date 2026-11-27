# Gestión de proyectos y documentos (issue #7) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el administrador cree, liste y borre proyectos, y suba (arrastrando, varios a la vez), vea, descargue y borre sus documentos adjuntos.

**Architecture:** Migración `004` con `proyectos` y `documentos` (BYTEA, `ON DELETE CASCADE`). Router `proyectos.py` con dos `APIRouter` protegidos por `require_admin`; las reglas de tipos y nombres de archivo en `documentos.py`; el SQL en `db.py`. Frontend: dos páginas (`/proyectos`, `/proyectos/:id`) y dos componentes reutilizables (`ConfirmDialog`, `DropZone`).

**Tech Stack:** FastAPI + psycopg 3 + Postgres 16 · `python-multipart` (nuevo) · React 19 + Vite + TS · pytest · Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-10-gestion-proyectos-design.md` (decisiones en `GUIA_ISSUE_7.md`).

## Global Constraints

- Solo administrador en todos los endpoints nuevos: 401 sin sesión, 403 si no es admin (`require_admin` de `app/deps.py`).
- Migración `api/migrations/004_proyectos.sql` (la `003` es de la issue #6), idempotente (`IF NOT EXISTS`). No tocar `db/init/` ni migraciones existentes.
- Todo el SQL en `api/app/db.py`, sección `# --- Proyectos (issue #7) ---` al final del fichero.
- Ficheros comunes con la #6 (`db.py`, `main.py`, `factories.py`, `Layout.tsx`, `App.tsx`, `client.ts`, `index.css`, `README.md`): solo añadir, no reordenar ni reformatear.
- `DOCUMENTO_MAX_MB` = 50 por defecto. Mensajes exactos: «Ya existe un proyecto con ese nombre», «Ya existe un documento con ese nombre en el proyecto», «El proyecto no existe», «El documento no existe», «Tipo de archivo no permitido», «El archivo pasa de 50 MB» (con el valor configurado), «El archivo está vacío».
- Nombres únicos sin distinguir mayúsculas: proyecto (global) y documento (por proyecto, extensión incluida).
- Cabeceras de toda descarga: `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, y `Content-Security-Policy: sandbox` salvo en PDF (corregido tras la revisión: el visor de Chrome no pinta PDF con sandbox).
- Cada fichero nuevo con cabecera (para qué, por qué, quién lo usa); comentarios del porqué; nada de «lo pidió X».
- Ningún test toca una bbdd real (FakeDB). TDD: test primero, verlo fallar, código, verlo pasar.
- Sin commits sin OK del usuario: el paso «Commit» de cada tarea es **dejar preparado el mensaje** (`feat: … (Refs #7)`); los commits se hacen al final con su OK.

## Review Focus

- Nombre con mayúsculas en la extensión (`INFORME.PDF`) → se reconoce como PDF (test en Tarea 2).
- Nombre con acentos y espacios (`Memoria técnica.pdf`) → se descarga con ese nombre (test en Tarea 2).
- Se borra el proyecto en otra pestaña mientras se suben archivos → cada archivo muestra «El proyecto no existe» y la pantalla no se rompe (test en Tarea 6).
- Arrastrar un archivo de 0 bytes (o una carpeta, que el navegador entrega vacía) → «El archivo está vacío» en ese archivo (tests en Tareas 4 y 6).
- Cerrar el modal con Escape o «Cancelar» → no se borra nada (test en Tarea 5).

## Orden y paralelismo

- En paralelo: Tareas 1, 2 y 5 (no comparten ficheros).
- Después: Tarea 3 (usa 1 y 2) → Tarea 4 (usa 3).
- Tarea 6 cuando estén 4 (contrato) y 5 (componentes). Tarea 7 al final.

---

### Task 1: Migración 004

**Files:**
- Create: `api/migrations/004_proyectos.sql`
- Test: `api/tests/test_migrations.py` (añadir)

**Interfaces:**
- Produces: tablas `proyectos(id, nombre, tipo, descripcion)` y `documentos(id, proyecto_id, nombre, contenido)`; índices únicos `proyectos_nombre_unico (lower(nombre))` y `documentos_nombre_unico (proyecto_id, lower(nombre))`.

- [ ] **Step 1: Test** `test_migracion_004_es_idempotente`, igual que `test_migracion_002_es_idempotente` pero con `004_proyectos.sql`; además `assert "ON DELETE CASCADE" in sql and "BYTEA" in sql`.
- [ ] **Step 2:** `cd api && pytest tests/test_migrations.py -q` → FAIL (no existe el fichero).
- [ ] **Step 3:** Crear el SQL exacto del spec (apartado «bbdd»), con cabecera de comentarios como la 001/002 (qué añade y por qué: cascada, unicidad sin mayúsculas, sin columna de tipo de archivo).
- [ ] **Step 4:** `pytest tests/test_migrations.py -q` → PASS.
- [ ] **Step 5:** Mensaje preparado: `feat: tablas de proyectos y documentos (Refs #7)`.

### Task 2: Reglas de archivos y configuración

**Files:**
- Create: `api/app/documentos.py`, `api/tests/test_documentos.py`
- Modify: `api/app/config.py` (campo nuevo), `api/tests/test_config.py`

**Interfaces:**
- Produces:
  - `Settings.documento_max_mb: int = Field(default=50, ge=1)`
  - `@dataclass(frozen=True) class TipoArchivo: content_type: str; visible: bool`
  - `tipo_de(nombre: str) -> TipoArchivo | None` (por extensión, sin distinguir mayúsculas)
  - `limpiar_nombre(nombre: str) -> str` (`ValueError` si queda vacío o > 255)
  - `content_disposition(nombre: str, inline: bool) -> str`

- [ ] **Step 1: Tests** en `test_documentos.py`:
  - `tipo_de("a.pdf") == TipoArchivo("application/pdf", True)`; `tipo_de("INFORME.PDF").content_type == "application/pdf"`; `tipo_de("notas.md") == TipoArchivo("text/plain; charset=utf-8", True)`; `tipo_de("x.png").visible`; `tipo_de("x.docx").visible is False`; `tipo_de("x.docx").content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"`.
  - Parametrizado: `tipo_de(n) is None` para `"x.html"`, `"x.svg"`, `"x.exe"`, `"sin_extension"`, `"x."`.
  - `limpiar_nombre("C:\\Users\\a\\informe.pdf") == "informe.pdf"`; `limpiar_nombre("../../etc/informe.pdf") == "informe.pdf"`; `limpiar_nombre("  a.pdf  ") == "a.pdf"`; `limpiar_nombre("a\x00b.pdf") == "ab.pdf"`; `ValueError` con `""`, `"   "` y `"a" * 252 + ".pdf"`.
  - `content_disposition("Memoria técnica.pdf", False) == "attachment; filename=\"Memoria tecnica.pdf\"; filename*=UTF-8''Memoria%20t%C3%A9cnica.pdf"`; con `inline=True` empieza por `inline;`.
  - En `test_config.py`: `make_settings().documento_max_mb == 50`; `make_settings(documento_max_mb=0)` → `ValidationError`.
- [ ] **Step 2:** `pytest tests/test_documentos.py tests/test_config.py -q` → FAIL.
- [ ] **Step 3:** Implementar. Tabla de extensiones del spec como un `dict` de extensión → `TipoArchivo` (MIME oficiales para Office/ODF; `image/jpeg` para `.jpg/.jpeg`). `content_disposition`: `filename=` en ASCII (`unicodedata.normalize("NFKD")` + quitar no-ASCII y comillas) y `filename*` con `urllib.parse.quote`.
- [ ] **Step 4:** Mismos tests → PASS. `ruff check .` limpio.
- [ ] **Step 5:** Mensaje preparado: `feat: reglas de tipos y nombres de documentos (Refs #7)`.

### Task 3: API de proyectos (crear, listar, detalle, borrar)

**Files:**
- Create: `api/app/routers/proyectos.py`, `api/tests/test_proyectos.py`
- Modify: `api/app/db.py` (sección al final), `api/app/main.py` (registrar router), `api/tests/factories.py` (FakeDB)

**Interfaces:**
- Consumes: `db.NombreDuplicado`, `require_admin`, `documentos.tipo_de` (para `visible`).
- Produces (db.py):
  - `list_projects(conn) -> list[dict]` → `{id, nombre, tipo, descripcion, num_documentos}` por `lower(nombre)`
  - `create_project(conn, nombre: str, tipo: str | None, descripcion: str | None) -> dict` (`NombreDuplicado`)
  - `get_project(conn, proyecto_id: int) -> dict | None` → proyecto + `documentos: [{id, nombre, tamano}]` por `lower(nombre)`, tamaño con `octet_length(contenido)`
  - `delete_project(conn, proyecto_id: int) -> bool`
- Produces (router): `router = APIRouter(prefix="/api/proyectos", dependencies=[Depends(require_admin)])`; el detalle añade `visible` a cada documento (`tipo_de(nombre).visible`).
- Produces (FakeDB): `self.proyectos = {}`, `self.documentos = {}` (id → `{"proyecto_id", "nombre", "contenido"}`), `next_project_id`, `next_document_id`; métodos con las mismas reglas (únicos con `.lower()`, cascada al borrar) y atajo `add_project(nombre, docs: dict[str, bytes] = {}) -> int`. Añadir los nombres a la lista de `install`.

- [ ] **Step 1: Tests** en `test_proyectos.py`, mismos fixtures que `test_roles.py` (`fake`, `anon`, `admin`, `login`, `ENDPOINTS`):
  - `test_sin_sesion_401` y `test_no_admin_403` parametrizados sobre los 4 endpoints de esta tarea (Tarea 4 añade los suyos a la misma lista).
  - Crear → 201 con `{id, nombre, tipo, descripcion, num_documentos: 0}`; espacios recortados; tipo y descripción vacíos → `None`.
  - Crear `"web"` con `"Web"` existente → 409 «Ya existe un proyecto con ese nombre».
  - 422: nombre vacío, nombre de 101 caracteres, descripción de 1001.
  - Listar ordenado sin mayúsculas (`"alfa"`, `"Beta"`) con `num_documentos` correcto (usar `fake.add_project`).
  - Detalle con documentos `{id, nombre, tamano, visible}` (`a.pdf` visible, `b.docx` no); inexistente → 404 «El proyecto no existe».
  - Borrar → 204 y sus documentos desaparecen de `fake.documentos`; inexistente → 404.
- [ ] **Step 2:** `pytest tests/test_proyectos.py -q` → FAIL.
- [ ] **Step 3:** Implementar db.py (SQL como roles: `UniqueViolation` → rollback + `NombreDuplicado`), FakeDB, router (`ProyectoIn` como `RolIn`: nombre 1–100, tipo ≤ 100, descripción ≤ 1000, vacíos → `None`) y `app.include_router(proyectos.router)` en `main.py`. Cabecera del router con el contrato completo (incluidos los endpoints de la Tarea 4).
- [ ] **Step 4:** `pytest -q` (suite entera) → PASS; `ruff check .` limpio.
- [ ] **Step 5:** Mensaje preparado: `feat: endpoints de gestión de proyectos (Refs #7)`.

### Task 4: API de documentos (subir, descargar, borrar) y límite de tamaño

**Files:**
- Modify: `api/app/routers/proyectos.py`, `api/app/db.py`, `api/app/main.py`, `api/tests/factories.py`, `api/requirements.txt` (`python-multipart==` última estable, fijada)
- Test: `api/tests/test_proyectos.py` (añadir)

**Interfaces:**
- Consumes: Tarea 2 (`tipo_de`, `limpiar_nombre`, `content_disposition`, `documento_max_mb`), Tarea 3.
- Produces (db.py): `add_document(conn, proyecto_id: int, nombre: str, contenido: bytes) -> dict | None` (`{id, nombre, tamano}`; `None` si no existe el proyecto; `NombreDuplicado`), `get_document(conn, documento_id: int) -> dict | None` (`{nombre, contenido}`), `delete_document(conn, documento_id: int) -> bool`.
- Produces (router): `POST /api/proyectos/{id}/documentos` (campo multipart `archivo: UploadFile`), y `documentos_router = APIRouter(prefix="/api/documentos", dependencies=[Depends(require_admin)])` con `GET /{id}` (query `ver: bool = False`) y `DELETE /{id}`.
- Produces (main.py): middleware HTTP que, para `POST` cuya ruta case `^/api/proyectos/\d+/documentos$`, responde 411 sin `Content-Length` y 413 «El archivo pasa de N MB» si `Content-Length > (documento_max_mb + 1) * 1024 * 1024`, sin leer el cuerpo.

- [ ] **Step 1: Tests** (con `files={"archivo": (nombre, bytes)}` del TestClient):
  - Añadir los 3 endpoints nuevos a `ENDPOINTS` (401/403 siguen pasando para todos).
  - Subir `a.pdf` → 201 `{id, nombre: "a.pdf", tamano: len}`; nombre `C:\\x\\a.pdf` → se guarda `a.pdf`.
  - 415 «Tipo de archivo no permitido» para `x.html`, `x.svg`, `x.exe`.
  - 422 «El archivo está vacío» con `b""`.
  - 409 «Ya existe un documento con ese nombre en el proyecto» con `A.PDF` tras `a.pdf`; `a.docx` tras `a.pdf` → 201.
  - 404 «El proyecto no existe» al subir a un proyecto inexistente.
  - 413 con `make_settings(documento_max_mb=1)` y 1 MB + 1 byte de contenido (comprobación del tamaño real).
  - 413 del middleware: `POST` con cabecera `Content-Length` de 10 GB y cuerpo pequeño → 413 sin pasar por el endpoint (FakeDB sin cambios).
  - Descargar: mismo contenido; `content-disposition` empieza por `attachment` sin `ver`; `inline` con `ver=1` en `.pdf`; `attachment` con `ver=1` en `.docx`; `content-type` correcto; las tres cabeceras de seguridad siempre; inexistente → 404 «El documento no existe».
  - Borrar documento → 204, y el detalle ya no lo lista; inexistente → 404.
- [ ] **Step 2:** `pytest tests/test_proyectos.py -q` → FAIL.
- [ ] **Step 3:** Implementar. Subida: `limpiar_nombre` (→ 422 si `ValueError`) → `tipo_de` (→ 415) → leer `await archivo.read(max + 1)` (→ 413 si pasa, 422 si vacío) → `db.add_document`. El endpoint de subida puede ser `async def` (por `await read`); el resto `def`. Descarga con `Response(content, media_type=…, headers=…)` y `# shortcut: carga el documento entero en memoria (≤ DOCUMENTO_MAX_MB), pasar a streaming si sube el límite`. Registrar `documentos_router` y el middleware en `main.py`.
- [ ] **Step 4:** `pip install -r requirements.txt` en el venv, `pytest -q` (suite entera) → PASS; `ruff check .` limpio.
- [ ] **Step 5:** Mensaje preparado: `feat: subir, ver, descargar y borrar documentos de un proyecto (Refs #7)`.

### Task 5: Cliente de API y componentes ConfirmDialog y DropZone

**Files:**
- Modify: `frontend/src/api/client.ts`, `frontend/src/api/client.test.ts`
- Create: `frontend/src/components/ConfirmDialog.tsx`, `frontend/src/components/DropZone.tsx`, `frontend/src/components/components.test.tsx`

**Interfaces:**
- Produces (client.ts):
  - `type Proyecto = { id: number; nombre: string; tipo: string | null; descripcion: string | null; num_documentos: number }`
  - `type Documento = { id: number; nombre: string; tamano: number; visible: boolean }`
  - `type ProyectoDetalle = Omit<Proyecto, 'num_documentos'> & { documentos: Documento[] }`
  - `listProjects(): Promise<Proyecto[]>`, `createProject(p: { nombre: string; tipo: string; descripcion: string }): Promise<Proyecto>`, `getProject(id: number): Promise<ProyectoDetalle>`, `deleteProject(id: number): Promise<void>`, `uploadDocument(proyectoId: number, file: File): Promise<Documento>`, `deleteDocument(id: number): Promise<void>`, `documentUrl(id: number, ver: boolean): string` (`/api/documentos/{id}` o `…?ver=1`)
  - `request()`: no pone `Content-Type: application/json` si `init.body instanceof FormData`.
- Produces (componentes):
  - `ConfirmDialog({ open, titulo, mensaje, confirmar, onConfirm, onCancel }: { open: boolean; titulo: string; mensaje: string; confirmar: string; onConfirm: () => void; onCancel: () => void })` con `<dialog>` (`showModal()`/`close()` en un efecto; el evento `cancel`, Escape, llama a `onCancel`); botón de confirmar con clase `peligro`.
  - `DropZone({ onFiles, disabled }: { onFiles: (files: File[]) => void; disabled?: boolean })`: zona con texto «Arrastra aquí los archivos o pulsa para elegirlos», `onDragOver` (con `preventDefault`), `onDrop`, y botón que abre un `<input type="file" multiple hidden>`; resalta mientras se arrastra encima (clase `encima`).

- [ ] **Step 1: Tests**:
  - `client.test.ts`: `uploadDocument(3, file)` hace `POST /api/proyectos/3/documentos` con `body instanceof FormData`, `body.get('archivo') === file` y sin cabecera `Content-Type`; `createProject` manda JSON; `documentUrl(5, true) === '/api/documentos/5?ver=1'` y `documentUrl(5, false) === '/api/documentos/5'`; un 409 de `createProject` lanza `ApiError` con el `detail`.
  - `components.test.tsx` (jsdom no implementa `showModal`: en `beforeAll`, `HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }` y `close` que lo quita):
    - `ConfirmDialog` abierto muestra título y mensaje; «Borrar» → `onConfirm`; «Cancelar» → `onCancel` y no `onConfirm`; evento `cancel` del dialog (Escape) → `onCancel`; con `open=false` no se ve.
    - `DropZone`: `fireEvent.drop` con `dataTransfer: { files: [a, b] }` → `onFiles([a, b])`; elegir con el input (`userEvent.upload`, `multiple`) → `onFiles`; `disabled` no llama.
- [ ] **Step 2:** `cd frontend && npm test` → FAIL.
- [ ] **Step 3:** Implementar (cabeceras de fichero; estilos `.dropzone`, `.dropzone.encima` y `dialog` en `index.css`, añadidos al final).
- [ ] **Step 4:** `npm test && npm run lint && npx tsc -b` → PASS.
- [ ] **Step 5:** Mensaje preparado: `feat: cliente de proyectos y componentes de aviso y arrastrar archivos (Refs #7)`.

### Task 6: Pantallas de proyectos, menú y rutas

**Files:**
- Create: `frontend/src/pages/Proyectos.tsx`, `frontend/src/pages/ProyectoDetalle.tsx`, `frontend/src/pages/Proyectos.test.tsx`
- Modify: `frontend/src/components/Layout.tsx` (entrada), `frontend/src/App.tsx` (2 rutas), `frontend/src/pages/pages.test.tsx` (menú y redirección), `frontend/src/index.css` (al final)

**Interfaces:**
- Consumes: Tarea 5 entera. Patrón de `Roles.tsx` (`.pagina`, errores de la API tal cual, recargar tras cada cambio).
- Produces: `ENTRADAS` += `{ to: '/proyectos', texto: 'Proyectos', soloAdmin: true }`; rutas `/proyectos` y `/proyectos/:id` dentro del `Layout`, con `user?.es_admin ? … : <Navigate to="/" replace />`.
- Constante en `ProyectoDetalle.tsx`: `MAX_MB = 50` con comentario (la API lo comprueba igual; aquí solo evita subir para nada).

- [ ] **Step 1: Tests** (`vi.mock('../api/client')`, `MemoryRouter`; detalle con `<Routes><Route path="/proyectos/:id" …/></Routes>` e `initialEntries={['/proyectos/1']}`):
  - Proyectos: lista nombre (enlace a `/proyectos/{id}`), tipo (`—` si null) y nº de documentos; sin proyectos → «Todavía no hay proyectos»; crear llama a `createProject` y recarga; 409 se muestra en `role="alert"`; «Borrar» abre el modal con el texto «Se borrarán también sus 3 documentos»; confirmar → `deleteProject(id)` y recarga; cancelar → no llama.
  - Detalle: muestra nombre, tipo y descripción; tabla de documentos con tamaño legible (`2048` → `2 KB`); «Ver» solo en los `visible` (enlace a `documentUrl(id, true)`, `target="_blank"`); «Descargar» con atributo `download`; borrar documento con modal → `deleteDocument`.
  - Subida: soltar `a.pdf` y `b.pdf` → `uploadDocument` dos veces y cada fila de estado termina en «Subido»; si `b.pdf` falla con `ApiError(409, 'Ya existe…')`, `a.pdf` queda «Subido» y `b.pdf` muestra el mensaje; un `File` de 51 MB (usar `Object.defineProperty(file, 'size', { value: 51 * 1024 * 1024 })`) → «El archivo pasa de 50 MB» sin llamar a `uploadDocument`; `ApiError(404, 'El proyecto no existe')` se muestra en su fila; `ApiError(422, 'El archivo está vacío')` también. Tras subir, vuelve a pedir `getProject`.
  - `pages.test.tsx`: admin ve «Proyectos» en el menú, un usuario normal no; `/proyectos` sin admin redirige a la home.
- [ ] **Step 2:** `npm test` → FAIL.
- [ ] **Step 3:** Implementar. El estado de subidas es una lista `{ nombre, estado: 'subiendo' | 'subido' | 'error', mensaje? }` mostrada bajo la `DropZone`; se sube en serie (`for … await`) para no saturar con 50 MB × N.
- [ ] **Step 4:** `npm test && npm run lint && npm run build` → PASS.
- [ ] **Step 5:** Mensaje preparado: `feat: menú y pantallas de gestión de proyectos (Refs #7)`.

### Task 7: Documentación y prueba de extremo a extremo

**Files:**
- Modify: `README.md` (variables, uso, API, «Cómo funciona», estructura), `.env.example` (`DOCUMENTO_MAX_MB=50` comentado), `GUIA_ISSUE_7.md` (apartados de cómo funciona, local)

- [ ] **Step 1:** README y `.env.example` con lo nuevo, siguiendo el estilo de las secciones de roles (solo añadir).
- [ ] **Step 2:** Suite completa: `cd api && pytest -q && ruff check .`; `cd frontend && npm test && npm run lint && npm run build` → todo PASS.
- [ ] **Step 3:** `docker compose up -d --build` sin `down -v` → `SELECT * FROM migraciones_aplicadas;` lista `004_proyectos.sql`.
- [ ] **Step 4:** En Chrome como admin: crear proyecto; nombre repetido con otras mayúsculas → error; arrastrar un PDF, un `.docx` y un `.html` → los dos primeros suben, el `.html` da «Tipo de archivo no permitido»; «Ver» el PDF abre en otra pestaña; «Descargar» el `.docx`; borrar un documento; borrar el proyecto (el modal dice cuántos documentos) → en psql no queda ningún documento de ese proyecto. Como usuario normal: no hay «Proyectos» y `/api/proyectos` da 403.
- [ ] **Step 5:** Mensaje preparado: `docs: README con la gestión de proyectos (Refs #7)`. Pasar al usuario la lista de commits con sus `git add`.
