-- Modelo de datos. Idempotente: se puede lanzar sobre una bbdd ya creada sin romper nada.
CREATE TABLE IF NOT EXISTS usuarios (
  id            SERIAL PRIMARY KEY,
  username      VARCHAR(50)  UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,   -- bcrypt, formato $2b$...
  creado_en     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
