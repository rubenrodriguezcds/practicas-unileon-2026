-- Usuario de prueba. El hash es bcrypt (el mismo formato que verifica la API);
-- la contraseña en claro no se sube: se comparte por el chat del equipo.
INSERT INTO usuarios (username, password_hash)
VALUES ('admin', '$2b$12$20pAwK8wCTj2/rY0h3l4WeWT9R3a5MbDjTUbuzMcVRmawsfYFIpb6')
ON CONFLICT (username) DO NOTHING;
