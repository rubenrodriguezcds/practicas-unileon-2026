# Asistente IA fase 1 (indexado) — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada documento subido a un proyecto se convierte con Docling, se trocea, se vectoriza y
se guarda en Postgres, con su estado visible en la ficha del proyecto y un buscador de prueba para
comprobar que la búsqueda funciona.

**Architecture:** Contenedor nuevo `indexador` que trabaja en segundo plano con una cola en
Postgres (`FOR UPDATE SKIP LOCKED`), habla con `docling` (sin puertos) y con la API de embeddings.
La API solo lee: estado de indexado en el detalle del proyecto y un endpoint de búsqueda híbrida
(vector + texto) para la página «Buscador».

**Tech Stack:** Python 3.12, psycopg 3, httpx, `vsdx`, LibreOffice sin interfaz,
`docling-serve-cpu` v1.38.2, Postgres 16 + pgvector (`halfvec`), OpenAI `text-embedding-3-small`
(1024 dimensiones), FastAPI, React + TypeScript.

**Spec:** `docs/superpowers/specs/2026-11-16-ia-fase1-indexado-design.md`

**Rama:** `feature/ia-indexado`, desde `prueba/extraccion-docling` (cambiado el 23-11: así trae ya
el servicio `docling` en el compose y los scripts de la prueba). El compose de esa rama publica la
interfaz de Docling en `127.0.0.1:5001`: **hay que quitar ese `ports:` en la Task 10**, antes de
llevar nada a `main`.

## Estado (23-11)

- **Tareas 1-6 hechas** (commits en la rama). **Tareas 7-13 pendientes**: las hace el compañero.
- Comprobado en real: la imagen del indexador construye; LibreOffice convierte `.doc`, `.ppt` y
  `.vsdx` a PDF dentro del contenedor; `docling_cliente.trocear` contra el Docling real devuelve
  trozos con sección, página, JSON y versión, y el `.doc` directo da `DoclingError`.
- **No** comprobado aún en real: el SQL de `cola.py` (se prueba en la Task 10 con la bbdd) y la
  migración 005 sobre la bbdd con pgvector (Task 1, paso 5: falta reconstruir `db`).

### Cambios respecto a lo escrito abajo (mandan sobre el texto de cada tarea)

1. **Task 4, cola**: un «error» se reintenta esperando `intentos` minutos (si Docling u OpenAI
   están caídos no se gastan los 3 intentos en segundos). Un «procesando» colgado que ya agotó los
   intentos pasa a «error». `marcar_hecho` **no** confirma (va dentro de la transacción de
   `guardar`); `marcar_error` hace `rollback` y confirma. `coger` confirma su propia transacción.
2. **Task 5, conversión**: en vez de `a_pdf` hay
   `convertir(nombre, contenido, destino) -> (nombre_nuevo, bytes)` y
   `camino(nombre) -> "docling" | "pdf" | "xlsx" | "visio" | None`. Cubre todos los tipos que
   acepta la subida (`api/app/documentos.py`): `.xls`/`.ods` → `.xlsx` (en PDF una hoja pierde la
   tabla), `.odt`/`.odp`/`.doc`/`.ppt`/`.vsd` → PDF, y `.gif`, `.webp`, `.txt` directos a Docling
   (comprobados). `None` = tipo no soportado → `marcar_error`.
3. **Task 6, Docling**: una sola llamada confirmada (`include_converted_doc=true`; el JSON está en
   `documents[0].content.json_content`). Firma `trocear(url, nombre, contenido, cliente=None)`
   (`cliente` solo para tests). Trozos de hasta 512 tokens (`chunking_max_tokens`). **El `text` de
   cada trozo ya lleva delante sus títulos**: se vectoriza `Trozo.texto` tal cual, sin añadirlos otra vez.
4. **Task 7, Visio**: hoy la subida **no acepta** `.vsdx` ni `.vsd` (`_TIPOS` en
   `api/app/documentos.py`). Hay que añadirlos ahí (`application/vnd.ms-visio.drawing` y
   `application/vnd.visio`, `visible=False`) con su test en `api/tests/test_documentos.py`.
   `Trozo` se importa de `docling_cliente`.
5. **Task 9**: `procesar` debe capturar también cualquier otra excepción (un fichero corrupto puede
   lanzar `zipfile.BadZipFile`, `KeyError`…) y llamar a `marcar_error` con el tipo y el mensaje,
   para que ningún documento se quede en «procesando» 30 min. El tipo `None` de `camino` → error.
6. **Task 10**: tras poner la API key, los documentos que ya agotaron sus 3 intentos siguen en
   «error»; para reintentarlos: `DELETE FROM indexado WHERE estado = 'error';` (apuntarlo en el README).
7. **Task 13, DECISIONES**: añadir la decisión de la cola en Postgres frente a RabbitMQ/Kafka
   (23-11): los tres son gratis, pero un broker añade un contenedor, obliga a tocar la subida y puede
   perder el aviso entre «guardar el documento» y «publicar el mensaje». RabbitMQ sería el paso
   siguiente si hiciera falta repartir el trabajo entre muchas máquinas; el cambio queda acotado a `cola.py`.

### Cómo probar el indexador

- Tests: `cd indexador && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest -q`.
- En real (con `docker compose up -d docling`): `docker build -t indexador-prueba indexador` y
  `docker run --rm --network practicas-unileon-2026_default indexador-prueba python -c "..."`
  llamando a `convertir` / `docling_cliente.trocear` con `http://docling:5001`.

## Global Constraints

- Un commit por tarea con el mensaje indicado en su paso «Commit»; push y PR cuando el equipo lo acuerde.
- Puertos publicados solo 80, 1521 y 22: `docling` e `indexador` sin `ports:`.
- Secretos solo en `.env`; variable nueva `OPENAI_API_KEY` también en `.env.example` y en la tabla
  del README.
- Cambios de esquema = migración nueva `api/migrations/005_indexado.sql`, idempotente.
- UTF-8 con LF; cabecera en cada fichero (para qué, por qué, quién lo usa); comentarios del porqué.
- TDD; ningún test usa servicios reales (bbdd, Docling, OpenAI se sustituyen por dobles).
- `cd api && pytest -q`, `cd indexador && pytest -q`, `cd frontend && npm test && npm run build`.
- Comentarios, commits y PRs sin mencionar quién pidió algo; Conventional Commits en español.
- APIs externas provisionales y con datos de prueba (spec, «Decidido»).
- Nada falla en silencio: todo error queda en el log y en `indexado.error`, y se ve en la ficha.

## Review Focus

1. **Documento borrado mientras se indexa**: guardar no debe fallar con violación de FK ni dejar
   trozos huérfanos; se descarta en silencio controlado (log) y sigue con el siguiente.
2. **Indexador arranca antes que la migración 005** (la aplica la API al arrancar): no debe morir;
   espera, avisa en el log y reintenta.
3. **Docling u OpenAI caídos o lentos**: el documento vuelve a quedar reintentable (`intentos`+1),
   y tras 3 fallos queda en `error` con el motivo legible.
4. **Documento sin texto** (PDF en blanco, imagen sin letras): termina en `hecho` con 0 trozos, no
   en bucle de reintentos.
5. **Búsqueda sin `OPENAI_API_KEY` o con la pregunta vacía**: 503 / 422 con mensaje claro, no 500.

## Mapa de ficheros

| Fichero | Responsabilidad |
|---|---|
| `db/Dockerfile` | `FROM pgvector/pgvector:pg16` |
| `api/migrations/005_indexado.sql` | Extensiones `vector`, `unaccent`; tablas `indexado`, `fragmentos`; índices |
| `api/app/db.py` | `get_project` con estado; `search_fragments` |
| `api/app/embeddings.py` | Vectorizar la pregunta del buscador |
| `api/app/routers/busqueda.py` | `GET /api/busqueda` (solo admin) |
| `indexador/` | `config.py`, `cola.py`, `convertir.py`, `docling_cliente.py`, `visio.py`, `embeddings.py`, `guardar.py`, `procesar.py`, `main.py`, `Dockerfile`, `requirements*.txt`, `tests/` |
| `docker-compose.yml` | Servicios `docling` e `indexador` |
| `frontend/src/pages/ProyectoDetalle.tsx` | Columna «Asistente» |
| `frontend/src/pages/Buscador.tsx` | Página de búsqueda de prueba |

`embeddings.py` existe en la API y en el indexador (unas 20 líneas cada uno): son contenedores
independientes y compartir código obligaría a un paquete común. Cambiar de proveedor = cambiar
los dos ficheros, con la misma firma.

---

### Task 1: Postgres con pgvector y migración 005

**Files:**
- Modify: `db/Dockerfile` (línea `FROM postgres:16` y su comentario de cabecera)
- Create: `api/migrations/005_indexado.sql`
- Test: `api/tests/test_migrations.py`

**Interfaces:**
- Produces: tablas `indexado(documento_id PK FK→documentos ON DELETE CASCADE, estado VARCHAR(20),
  intentos INT DEFAULT 0, error TEXT, docling_json JSONB, docling_version VARCHAR(20),
  actualizado TIMESTAMPTZ DEFAULT now())` y `fragmentos(id SERIAL, documento_id FK CASCADE,
  proyecto_id FK→proyectos CASCADE, orden INT, texto TEXT, titulos TEXT[], paginas INT[],
  embedding halfvec(1024), busqueda tsvector)`. Índices: HNSW `halfvec_cosine_ops` en
  `embedding`, GIN en `busqueda`, btree en `proyecto_id` y en `documento_id`.

- [x] **Step 1:** Añadir a `test_migrations.py` `test_005_es_idempotente`: lee el fichero y
  comprueba que todo `CREATE TABLE`, `CREATE INDEX` y `CREATE EXTENSION` lleva `IF NOT EXISTS`
  (mismo estilo que el test de las migraciones de #4 y #5).
- [x] **Step 2:** `cd api && pytest tests/test_migrations.py -q` → FAIL (no existe el fichero).
- [x] **Step 3:** Escribir la migración con la cabecera explicativa del estilo de `004`.
- [x] **Step 4:** `pytest -q` → PASS, suite entera.
- [x] **Step 5:** Comprobar en real: `docker compose build db && docker compose up -d` con el volumen
  existente (la imagen pgvector usa el mismo formato de datos de Postgres 16, no hace falta
  `down -v`); `docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c '\dx'` muestra
  `vector` y `unaccent`, y `\d fragmentos` la tabla.
- [x] **Step 6:** Commit: `feat(bbdd): pgvector y tablas de indexado`.

### Task 2: Estado de indexado en el detalle del proyecto (API)

**Files:**
- Modify: `api/app/db.py:366` (`get_project`), `api/tests/factories.py` (FakeDB)
- Test: `api/tests/test_proyectos.py`

**Interfaces:**
- Produces: cada documento de `GET /api/proyectos/{id}` lleva `indexado: {"estado":
  "pendiente"|"procesando"|"hecho"|"error", "error": str|None, "fragmentos": int}`. Sin fila en
  `indexado` → `"pendiente"`.
- FakeDB: `self.indexado = {}` (documento_id → dict) y `self.fragmentos = {}` (documento_id → n).

- [x] **Step 1:** Tests: `test_detalle_documento_sin_indexar_sale_pendiente` y
  `test_detalle_documento_con_error_muestra_el_motivo` (rellenando `fake.indexado`).
- [x] **Step 2:** `pytest tests/test_proyectos.py -q` → FAIL (falta la clave `indexado`).
- [x] **Step 3:** `get_project`: `LEFT JOIN indexado` y subconsulta `count(*)` de fragmentos;
  `coalesce(estado, 'pendiente')`. FakeDB igual.
- [x] **Step 4:** `pytest -q` → PASS.
- [x] **Step 5:** Commit: `feat(api): estado de indexado de cada documento`.

### Task 3: Columna «Asistente» en la ficha del proyecto

**Files:**
- Modify: `frontend/src/api/client.ts` (tipo del documento), `frontend/src/pages/ProyectoDetalle.tsx`, `frontend/src/index.css`
- Test: `frontend/src/pages/Proyectos.test.tsx` (o el test donde ya se prueba el detalle)

**Interfaces:**
- Consumes: `indexado` de Task 2.
- Textos fijos: `pendiente` → «Pendiente», `procesando` → «Indexando…», `hecho` → «Listo (N
  trozos)», `error` → «Error» con el motivo en `title` y visible al pasar el ratón.
- Mientras algún documento esté pendiente o procesando, la ficha se refresca cada 5 s.

- [x] **Step 1:** Tests: los cuatro textos, y que con un documento «procesando» se vuelve a pedir
  el detalle (temporizadores falsos de Vitest).
- [x] **Step 2:** `npm test` → FAIL.
- [x] **Step 3:** Implementar la columna y el refresco (parar el intervalo al desmontar).
- [x] **Step 4:** `npm test && npm run build` → PASS; mirarlo en el navegador.
- [x] **Step 5:** Commit: `feat(web): estado del asistente en la ficha del proyecto`.

### Task 4: Esqueleto del indexador y cola

**Files:**
- Create: `indexador/Dockerfile`, `indexador/requirements.txt`, `indexador/requirements-dev.txt`,
  `indexador/pytest.ini`, `indexador/config.py`, `indexador/cola.py`, `indexador/tests/test_config.py`

**Interfaces:**
- `config.py`: `Config(db_dsn: str, docling_url: str, openai_api_key: str | None,
  max_intentos: int = 3, colgado_min: int = 30, espera_s: int = 5)` y `leer_config(env) -> Config`
  (valida en la frontera: falta de `POSTGRES_*` → error claro; falta de API key → `None`, no error).
- `cola.py`:
  - `coger(conn, cfg) -> dict | None` — en una transacción: elige un documento sin fila en
    `indexado`, o con `estado='error' AND intentos < max`, o `procesando` con `actualizado` más
    antiguo que `colgado_min`; `FOR UPDATE SKIP LOCKED`; hace upsert a `procesando` e
    `intentos+1`; devuelve `{id, proyecto_id, nombre, contenido}`.
  - `marcar_hecho(conn, documento_id, docling_json, version)`; `marcar_error(conn, documento_id, motivo)`.
- Dockerfile: `python:3.12-slim` + `libreoffice-writer-nogui libreoffice-impress-nogui
  libreoffice-calc-nogui libreoffice-draw-nogui fonts-dejavu-core`; usuario sin root;
  `CMD ["python", "main.py"]`.
- `requirements.txt`: `psycopg[binary]==3.3.6`, `httpx==0.28.1`, `vsdx==0.6.1`.

- [x] **Step 1:** Tests de `leer_config`: valores por defecto, error sin `POSTGRES_PASSWORD`, API key ausente → `None`.
- [x] **Step 2:** `cd indexador && pytest -q` → FAIL.
- [x] **Step 3:** Implementar `config.py` y `cola.py` (el SQL de `cola.py` se comprueba en real en Task 10).
- [x] **Step 4:** `pytest -q` → PASS.
- [x] **Step 5:** Commit: `feat(indexador): configuración y cola de documentos`.

### Task 5: Conversión previa con LibreOffice

**Files:** Create `indexador/convertir.py`; Test `indexador/tests/test_convertir.py`

**Interfaces:**
- `camino(nombre: str) -> str` — `"docling"` (pdf, docx, pptx, xlsx, imágenes, txt, csv, md),
  `"pdf_primero"` (doc, ppt, vsd), `"visio"` (vsdx: PDF + `visio.py`).
- `a_pdf(nombre: str, contenido: bytes) -> bytes` — escribe en un directorio temporal, ejecuta
  `soffice --headless --convert-to pdf`, devuelve el PDF; `ConversionError` con el stderr si falla
  o tarda más de 120 s.

- [x] **Step 1:** Tests: tabla de extensiones de la spec (mayúsculas incluidas: `INFORME.PDF`) y
  `a_pdf` con `subprocess.run` sustituido (éxito, código ≠ 0, timeout).
- [x] **Step 2:** `pytest tests/test_convertir.py -q` → FAIL.
- [x] **Step 3:** Implementar.
- [x] **Step 4:** `pytest -q` → PASS.
- [x] **Step 5:** Commit: `feat(indexador): conversión a PDF con LibreOffice`.

### Task 6: Cliente de Docling

**Files:** Create `indexador/docling_cliente.py`; Test `indexador/tests/test_docling_cliente.py`

**Interfaces:**
- `trocear(url: str, nombre: str, contenido: bytes) -> Resultado` donde
  `Resultado(trozos: list[Trozo], docling_json: dict, version: str)` y
  `Trozo(texto: str, titulos: list[str], paginas: list[int])`.
- Opciones fijas: `ocr_lang=["es"]`, `table_mode="accurate"`, `image_export_mode="placeholder"`, timeout 900 s.
- `DoclingError` con el mensaje de Docling si `status != "success"` o HTTP ≠ 200.

- [x] **Step 1:** Comprobar contra el `docling` real (rama de prueba) si `POST /v1/chunk/hybrid/file`
  con `to_formats=json` devuelve el JSON del documento en `documents`. Si sí: una sola llamada.
  Si no: `/v1/convert/file` (json) + `/v1/chunk/hybrid/file`. Apuntar el resultado en la cabecera
  del fichero. `version` sale de `GET /version` (campo `docling-serve`).
- [x] **Step 2:** Tests con `httpx.MockTransport` y respuestas grabadas de la prueba: trozos
  bien mapeados, `page_numbers` vacío en Word → `[]`, `failure` → `DoclingError`, 500 → `DoclingError`.
- [x] **Step 3:** `pytest tests/test_docling_cliente.py -q` → FAIL. Implementar. → PASS.
- [x] **Step 4:** Commit: `feat(indexador): cliente de Docling`.

### Task 7: Visio

**Files:** Create `indexador/visio.py` (a partir de `prueba_docling/visio.py`); Test
`indexador/tests/test_visio.py` + `indexador/tests/datos/arquitectura.vsdx` (la muestra ficticia).

**Interfaces:**
- `trozos_visio(contenido: bytes) -> list[Trozo]` — un trozo por página:
  `titulos=["Diagrama: <página>"]`, `paginas=[n]`, texto = formas + «Conexiones: A → B».

- [ ] **Step 1:** Test con la muestra: contiene «Usuarios → Portal de facturación».
- [ ] **Step 2:** FAIL → implementar → PASS.
- [ ] **Step 3:** Commit: `feat(indexador): texto y conexiones de Visio`.

### Task 8: Embeddings del indexador

**Files:** Create `indexador/embeddings.py`; Test `indexador/tests/test_embeddings.py`

**Interfaces:**
- `vectorizar(textos: list[str], api_key: str | None) -> list[list[float]]` — `POST
  https://api.openai.com/v1/embeddings`, `model="text-embedding-3-small"`, `dimensions=1024`,
  lotes de 100 textos; `EmbeddingsError("falta OPENAI_API_KEY")` si no hay clave; otro
  `EmbeddingsError` con el mensaje del proveedor si HTTP ≠ 200. Lista vacía → lista vacía sin llamar.

- [ ] **Step 1:** Tests con `MockTransport`: 250 textos → 3 peticiones y orden conservado; sin clave; 401; lista vacía.
- [ ] **Step 2:** FAIL → implementar → PASS.
- [ ] **Step 3:** Commit: `feat(indexador): embeddings`.

### Task 9: Procesar un documento y bucle principal

**Files:** Create `indexador/guardar.py`, `indexador/procesar.py`, `indexador/main.py`; Test `indexador/tests/test_procesar.py`

**Interfaces:**
- `guardar.guardar(conn, doc: dict, trozos: list[Trozo], vectores, resultado) -> None` — en una
  transacción: borra fragmentos previos del documento, inserta los nuevos con
  `busqueda = to_tsvector('spanish', unaccent(titulos || texto))`, llama a `cola.marcar_hecho`. Si
  el documento ya no existe (FK), hace rollback y lo registra en el log.
- `procesar.procesar(doc: dict, cfg, docling, embeddings, guardar) -> None` — orquesta: `camino` →
  (`a_pdf`) → `trocear` → (+ `trozos_visio`) → `vectorizar` → `guardar`. Cualquier
  `ConversionError | DoclingError | EmbeddingsError` → `marcar_error` con el motivo. Las
  dependencias entran como parámetros para poder usar dobles.
- `main.py`: bucle `coger` → `procesar`; sin trabajo, duerme `espera_s`; si falta la tabla
  `indexado` (migración aún no aplicada) o la bbdd no responde, log y reintento a los 10 s.

- [ ] **Step 1:** Tests con dobles: PDF normal → `guardar` recibe trozos y vectores; `.doc` pasa por
  `a_pdf`; `.vsdx` añade los trozos de Visio; Docling falla → `marcar_error` con su mensaje;
  documento sin texto → `hecho` con 0 trozos y sin llamar a embeddings.
- [ ] **Step 2:** FAIL → implementar → PASS (suite del indexador entera).
- [ ] **Step 3:** Commit: `feat(indexador): procesado de documentos`.

### Task 10: Compose y prueba de punta a punta

**Files:** Modify `docker-compose.yml`, `.env.example`, `README.md` (tabla de variables y servicios)

**Interfaces:**
- `docling`: imagen `quay.io/docling-project/docling-serve-cpu:v1.38.2`,
  `DOCLING_SERVE_MAX_SYNC_WAIT=900`, healthcheck `/health`, **sin `ports`**.
- `indexador`: `build: ./indexador`, `env_file: .env`, `DB_HOST=db`, `DOCLING_URL=http://docling:5001`,
  `depends_on` db y docling sanos, `restart: unless-stopped`, sin `ports`.

- [ ] **Step 1:** Añadir servicios y `OPENAI_API_KEY=` a `.env.example` y al README.
- [ ] **Step 2:** `docker compose up -d --build`; subir desde la web las muestras de
  `prueba_docling/muestras/` (ficticias) a un proyecto de prueba.
- [ ] **Step 3:** Ver en la ficha cómo pasan de «Pendiente» a «Listo (N trozos)»; con DBeaver o
  `psql`, `SELECT documento_id, orden, titulos, paginas, left(texto, 80) FROM fragmentos`.
- [ ] **Step 4:** Casos a mano: quitar `OPENAI_API_KEY` → «Error: falta OPENAI_API_KEY» en la ficha;
  `docker compose stop docling` → reintentos en el log; borrar un documento → sus fragmentos desaparecen.
- [ ] **Step 5:** Commit: `feat(ia): servicios docling e indexador`.

### Task 11: Endpoint de búsqueda

**Files:** Create `api/app/embeddings.py`, `api/app/routers/busqueda.py`; Modify `api/app/db.py`,
`api/app/main.py` (registrar router), `api/app/config.py` (`openai_api_key: str | None = None`),
`api/requirements.txt` (`httpx`), `api/tests/factories.py`; Test `api/tests/test_busqueda.py`

**Interfaces:**
- `embeddings.vectorizar_pregunta(texto: str, api_key: str | None) -> list[float]` (mismo modelo y dimensiones que el indexador).
- `db.search_fragments(conn, vector: list[float], texto: str, proyecto_id: int | None, k: int = 10) -> list[dict]`
  — dos rankings (coseno sobre `embedding`, `ts_rank` sobre `busqueda` con
  `websearch_to_tsquery('spanish', unaccent(texto))`), 30 candidatos cada uno, combinados con RRF
  (`1/(60+rank)`); cada resultado: `documento_id, documento, proyecto_id, proyecto, titulos,
  paginas, texto, puntuacion_vector, puntuacion_texto, puntuacion`.
- `GET /api/busqueda?q=&proyecto_id=` — solo admin (`require_admin`); `q` vacío o > 500
  caracteres → 422; sin API key → 503 «Falta OPENAI_API_KEY: el buscador no está disponible»;
  error del proveedor → 502 con su mensaje.

- [ ] **Step 1:** Tests con FakeDB y `vectorizar_pregunta` sustituido: 401/403, 422, 503, resultados
  en orden, filtro por proyecto pasado a la bbdd.
- [ ] **Step 2:** FAIL → implementar → PASS (suite de la API entera).
- [ ] **Step 3:** Probar el SQL en real con las muestras indexadas (Task 10): «¿cuánto cuesta la
  migración?» debe traer el resumen de `memoria.docx`/`informe.pdf` arriba.
- [ ] **Step 4:** Commit: `feat(api): búsqueda híbrida en los documentos`.

### Task 12: Página «Buscador»

**Files:** Create `frontend/src/pages/Buscador.tsx`; Modify `frontend/src/App.tsx` (ruta
`/buscador`, solo admin), `frontend/src/components/Layout.tsx` (entrada «Buscador»),
`frontend/src/api/client.ts`, `frontend/src/index.css`; Test `frontend/src/pages/Buscador.test.tsx`

**Interfaces:**
- Consumes: `GET /api/busqueda` (Task 11).
- Pantalla: campo de pregunta, desplegable «Todos los proyectos» / cada proyecto, botón
  «Buscar». Cada resultado: documento y proyecto (enlace a la ficha), sección, páginas, texto del
  trozo y las tres puntuaciones (significado, palabras, combinada) con 3 decimales. Sin
  resultados: «No hay trozos que se parezcan». Errores de la API: el mensaje tal cual.

- [ ] **Step 1:** Tests: pinta resultados, envía `proyecto_id`, muestra el 503, la ruta redirige si no es admin.
- [ ] **Step 2:** FAIL → implementar → PASS; `npm run build`; mirarlo en el navegador con las muestras.
- [ ] **Step 3:** Commit: `feat(web): página de buscador de prueba`.

### Task 13: Documentación y revisión final

**Files:** Modify `README.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `DECISIONES_Y_PENDIENTES.md`

- [ ] **Step 1:** README: servicios nuevos, cómo ver lo indexado con DBeaver (`localhost:1521`) y el buscador.
- [ ] **Step 2:** ARCHITECTURE: por qué indexador aparte, cola en Postgres, `halfvec(1024)`, módulo único de vectores.
- [ ] **Step 3:** DECISIONES: decisiones nuevas (pgvector ahora → Qdrant/Pinecone al escalar; APIs
  provisionales → modelos locales con el servidor; no guardar Markdown) y pendientes (reindexar al
  cambiar de modelo, descripción de imágenes, permisos por proyecto en la búsqueda).
- [ ] **Step 4:** Las tres suites y el build en verde; revisión de toda la rama por alguien que no la escribió.
- [ ] **Step 5:** Commit: `docs: indexado de documentos para el asistente`. PR cuando el equipo lo acuerde.
