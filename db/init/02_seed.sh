#!/bin/sh
# Usuario admin de la web con la contraseña del .env (APP_ADMIN_PASSWORD), así ninguna
# contraseña de la aplicación vive en el repositorio. Postgres genera el hash bcrypt
# (pgcrypto, formato $2a$), que es el que verifica la API.
set -e

: "${APP_ADMIN_PASSWORD:?Falta APP_ADMIN_PASSWORD en el .env}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v pw="$APP_ADMIN_PASSWORD" <<'EOSQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
INSERT INTO usuarios (username, password_hash)
VALUES ('admin', crypt(:'pw', gen_salt('bf', 12)))
ON CONFLICT (username) DO NOTHING;
EOSQL
