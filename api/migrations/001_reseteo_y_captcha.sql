-- Issue #4: reseteo de contraseña y captcha.
--
-- Qué añade:
--   - usuarios.email: a dónde se envía la contraseña nueva del reseteo.
--   - usuarios.reset_hash / reset_expira: la contraseña del reseteo queda PENDIENTE una hora y la
--     vieja sigue valiendo hasta que se entra con la nueva. Así, quien sepa un nombre de usuario
--     no puede dejarlo sin acceso pidiendo reseteos.
--   - captchas_usados: firmas de retos ALTCHA ya usados, para que un reto valga una sola vez.
--   - intentos_reset: intentos de reseteo por usuario y por IP, para el límite por hora.
--
-- Se guarda en la bbdd y no en memoria de la API para que sobreviva a reinicios y valga aunque
-- haya varias copias de la API. Idempotente (IF NOT EXISTS), como los scripts de init.

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email        VARCHAR(255);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS reset_hash   VARCHAR(255);  -- bcrypt, como password_hash
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS reset_expira TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS captchas_usados (
  firma  TEXT        PRIMARY KEY,   -- firma HMAC del reto (única por reto)
  expira TIMESTAMPTZ NOT NULL       -- a partir de aquí el reto ya no vale y la fila se borra
);

CREATE TABLE IF NOT EXISTS intentos_reset (
  id        SERIAL      PRIMARY KEY,
  clave     TEXT        NOT NULL,                -- 'usuario:<nombre>' o 'ip:<dirección>'
  creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS intentos_reset_clave_fecha ON intentos_reset (clave, creado_en);
