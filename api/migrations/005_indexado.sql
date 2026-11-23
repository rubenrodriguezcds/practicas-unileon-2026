-- Asistente IA, fase 1: indexado de los documentos para buscarlos por significado y por palabras.
--
-- Qué añade:
--   - extensiones `vector` (pgvector: columnas de vectores e índices HNSW) y `unaccent` (buscar
--     sin acentos). Exigen la imagen `pgvector/pgvector:pg16` (db/Dockerfile).
--   - indexado: una fila por documento que el indexador ha cogido. Sin fila = pendiente: así la
--     subida no cambia y ningún documento se queda fuera de la cola (el estado se deriva).
--     `docling_json` guarda el documento convertido para volver a trocearlo sin reprocesar el
--     original.
--   - fragmentos: los trozos de cada documento con su sección y páginas (para citar), su vector
--     y su texto preparado para la búsqueda por palabras. `proyecto_id` está duplicado a propósito
--     para filtrar por proyecto sin unir con documentos.
--
-- Vectores: halfvec(1024) ocupa la mitad que vector(1024) con pérdida despreciable. 1024 es lo que
-- se pide a OpenAI y el tamaño de los modelos locales candidatos (bge-m3): cambiar de modelo no
-- cambia la tabla (sí exige revectorizar).
--
-- `busqueda` la rellena el indexador (to_tsvector('spanish', unaccent(...))): unaccent no es
-- IMMUTABLE y no puede ir en una columna generada.
--
-- Borrados: borrar un documento o un proyecto borra su estado y sus trozos (ON DELETE CASCADE).
--
-- Idempotente (IF NOT EXISTS), como las anteriores.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS indexado (
  documento_id    INTEGER     PRIMARY KEY REFERENCES documentos (id) ON DELETE CASCADE,
  estado          VARCHAR(20) NOT NULL,   -- procesando | hecho | error
  intentos        INTEGER     NOT NULL DEFAULT 0,
  error           TEXT,
  docling_json    JSONB,
  docling_version VARCHAR(20),
  actualizado     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fragmentos (
  id           SERIAL  PRIMARY KEY,
  documento_id INTEGER NOT NULL REFERENCES documentos (id) ON DELETE CASCADE,
  proyecto_id  INTEGER NOT NULL REFERENCES proyectos (id) ON DELETE CASCADE,
  orden        INTEGER NOT NULL,
  texto        TEXT    NOT NULL,
  titulos      TEXT[]  NOT NULL DEFAULT '{}',
  paginas      INTEGER[] NOT NULL DEFAULT '{}',  -- vacío en Word (no tiene páginas fijas)
  embedding    halfvec(1024),
  busqueda     tsvector
);
CREATE INDEX IF NOT EXISTS fragmentos_embedding ON fragmentos USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS fragmentos_busqueda ON fragmentos USING gin (busqueda);
CREATE INDEX IF NOT EXISTS fragmentos_proyecto ON fragmentos (proyecto_id);
CREATE INDEX IF NOT EXISTS fragmentos_documento ON fragmentos (documento_id);
