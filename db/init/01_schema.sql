-- Modelo de datos: crea las tablas de la aplicación.
--
-- Para qué: es el script que pide el enunciado para que, si el modelo no existe, se cree desde
-- cero al arrancar.
--
-- Cuándo se ejecuta: la imagen de Postgres lanza automáticamente los ficheros de
-- /docker-entrypoint-initdb.d (en orden alfabético: este y luego 02_seed.sh) la primera vez,
-- cuando el volumen de datos está vacío. Para volver a lanzarlo: `docker compose down -v`.
--
-- Por qué es idempotente (IF NOT EXISTS): se puede ejecutar a mano sobre una bbdd que ya
-- existe sin romper ni duplicar nada.
--
-- Quién lo usa: la API (app/db.py) lee la tabla `usuarios` para el login.

-- Usuarios que pueden iniciar sesión en la aplicación web.
CREATE TABLE IF NOT EXISTS usuarios (
  id            SERIAL PRIMARY KEY,
  username      VARCHAR(50)  UNIQUE NOT NULL,   -- nombre con el que se inicia sesión
  password_hash VARCHAR(255) NOT NULL,          -- hash bcrypt ($2a$ o $2b$); nunca la contraseña en claro
  creado_en     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
