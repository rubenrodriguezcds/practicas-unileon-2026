-- Issue #7: gestión de proyectos y documentos.
--
-- Qué añade:
--   - proyectos: los proyectos del gestor. `nombre` es único sin distinguir mayúsculas (global),
--     porque es lo que el administrador ve y elige; dos proyectos con el mismo nombre serían
--     indistinguibles. `tipo` es libre y opcional.
--   - documentos: los ficheros de cada proyecto. `contenido` es BYTEA porque se guarda el fichero
--     tal cual. No hay columna de tipo de archivo: el tipo se deduce de la extensión del nombre.
--     El nombre es único dentro de su proyecto, sin distinguir mayúsculas (la extensión incluida).
--
-- Borrados:
--   - Borrar un proyecto borra sus documentos (ON DELETE CASCADE): un documento sin proyecto no
--     tiene sentido, y la bbdd lo garantiza aunque algo se salte la API.
--
-- Unicidad: los índices sobre lower(...) hacen que la bbdd cumpla «sin distinguir mayúsculas» y
-- evitan carreras entre dos peticiones simultáneas (la API responde 409 al violar el índice).
--
-- Idempotente (IF NOT EXISTS), como las anteriores.

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
-- El mismo índice sirve para buscar los documentos de un proyecto (proyecto_id es su primera columna).
CREATE UNIQUE INDEX IF NOT EXISTS documentos_nombre_unico ON documentos (proyecto_id, lower(nombre));
