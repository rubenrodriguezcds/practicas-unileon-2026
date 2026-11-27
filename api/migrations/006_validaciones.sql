-- Validaciones de contenido por proyecto (diseño: docs/superpowers/specs/2026-11-27-validaciones-design.md).
--
-- Qué añade:
--   - validaciones: lo que se comprueba en cada proyecto para darlo por completo, p. ej. «aparecen
--     las VLAN» o «está definida la tabla de rutas». Dos tipos:
--       · patron: `criterio` es una expresión regular de Postgres que se busca en el texto de los
--         trozos del proyecto (exacta y rápida).
--       · ia: `criterio` es una pregunta; se buscan los trozos parecidos y un modelo de lenguaje
--         responde si se cumple, citando el trozo.
--     `orden` es el orden en que se muestran (el de creación).
--   - validacion_resultados: el ÚLTIMO resultado de cada validación (se sobrescribe al volver a
--     validar). Sin fila = sin validar, como `indexado`: el estado se deriva. `resumen` es el resumen
--     corto de la IA (solo en las de IA) que se ve al desplegar las pruebas.
--   - validacion_pruebas: los trozos que lo demuestran, en orden (un patrón: el primero de cada
--     documento donde aparece; la IA: los que cita).
--
-- Borrados:
--   - Borrar un proyecto borra sus validaciones, y una validación su resultado (CASCADE).
--   - Si se borra o se reindexa un documento, sus trozos dejan de ser prueba (CASCADE en
--     validacion_pruebas); el resultado se queda, y basta con volver a validar.
--
-- Idempotente (IF NOT EXISTS), como las anteriores.

CREATE TABLE IF NOT EXISTS validaciones (
  id          SERIAL       PRIMARY KEY,
  proyecto_id INTEGER      NOT NULL REFERENCES proyectos (id) ON DELETE CASCADE,
  nombre      VARCHAR(200) NOT NULL,
  tipo        VARCHAR(10)  NOT NULL CHECK (tipo IN ('patron', 'ia')),
  criterio    TEXT         NOT NULL,
  orden       INTEGER      NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS validaciones_proyecto ON validaciones (proyecto_id);

CREATE TABLE IF NOT EXISTS validacion_resultados (
  validacion_id INTEGER     PRIMARY KEY REFERENCES validaciones (id) ON DELETE CASCADE,
  estado        VARCHAR(10) NOT NULL CHECK (estado IN ('ok', 'falla', 'error')),
  explicacion   TEXT,
  resumen       TEXT,
  ejecutada     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS validacion_pruebas (
  validacion_id INTEGER NOT NULL REFERENCES validacion_resultados (validacion_id) ON DELETE CASCADE,
  fragmento_id  INTEGER NOT NULL REFERENCES fragmentos (id) ON DELETE CASCADE,
  orden         INTEGER NOT NULL,
  PRIMARY KEY (validacion_id, fragmento_id)
);
