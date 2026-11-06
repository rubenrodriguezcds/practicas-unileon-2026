-- Issue #5: gestión de roles.
--
-- Qué añade:
--   - usuarios.es_admin: marca al administrador, el único que puede gestionar roles (lo pide la
--     issue: «una columna en bbdd de tipo booleano»). Por defecto false: un usuario nuevo nunca
--     es administrador sin que se diga expresamente. Se marca al usuario 'admin' del seed.
--   - roles: los roles de la aplicación. `nombre` es único porque es lo que el administrador ve y
--     elige; dos roles con el mismo nombre serían indistinguibles.
--   - usuario_roles: qué usuarios tienen cada rol. Un usuario puede tener varios roles, por eso es
--     una tabla aparte y no una columna rol_id en usuarios.
--
-- Borrados:
--   - Borrar un usuario le quita sus roles (ON DELETE CASCADE): la asignación no tiene sentido sin él.
--   - Borrar un rol que tiene usuarios lo impide la bbdd (ON DELETE RESTRICT). La API comprueba
--     antes y responde 409 con un mensaje claro; la restricción es la red por si algo se salta la API.
--
-- Idempotente (IF NOT EXISTS), como la 001.

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS es_admin BOOLEAN NOT NULL DEFAULT false;
UPDATE usuarios SET es_admin = true WHERE username = 'admin';

CREATE TABLE IF NOT EXISTS roles (
  id          SERIAL       PRIMARY KEY,
  nombre      VARCHAR(100) NOT NULL UNIQUE,
  descripcion TEXT
);

CREATE TABLE IF NOT EXISTS usuario_roles (
  usuario_id INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
  rol_id     INTEGER NOT NULL REFERENCES roles (id)    ON DELETE RESTRICT,
  PRIMARY KEY (usuario_id, rol_id)
);
-- La clave primaria ya sirve para buscar por usuario; este índice es para «usuarios con el rol X».
CREATE INDEX IF NOT EXISTS usuario_roles_rol ON usuario_roles (rol_id);
