# Issue #4 — Login: logo, reseteo de contraseña y captcha

Rama: `feature/login-mejoras-#4` (sale de `feature/docker-entorno`; cuando esa PR entre en
`main`, la PR de esta rama contra `main` solo mostrará los commits de la issue).

## Qué pide la issue

1. Logo arriba a la izquierda en la pantalla de login.
2. Botón de reseteo de contraseña: envía por correo una contraseña nueva autogenerada.
3. Chequeo de que no es un bot.
4. Tests.

## Criterios de aceptación

- El logo (`frontend/public/cds-logo.png`) aparece arriba a la izquierda **solo** en `/login`
  y `/reset-password`. No se toca ningún layout compartido ni menú.
- En login hay un enlace «¿Olvidaste tu contraseña?» que lleva a `/reset-password`.
- `/reset-password` pide usuario + captcha y siempre muestra el mismo mensaje genérico.
- Login y reseteo exigen captcha ALTCHA válido, caducado a los 5 min y de un solo uso.
- Tras un fallo de login o de reseteo, el widget se reinicia con un reto nuevo.
- La contraseña nueva llega por correo; la vieja **sigue valiendo** hasta que se entra con la
  nueva (ver «Seguridad»).
- Ninguna bbdd existente necesita `docker compose down -v`: las columnas y tablas nuevas se
  añaden con migraciones al arrancar la API.
- `pytest`, `ruff check`, `npm test`, `npm run lint` y `npm run build` en verde.

## Seguridad: por qué el reseteo no cambia la contraseña al momento

Si el reseteo sustituyera la contraseña en cuanto se pide, cualquiera que conozca un nombre de
usuario podría dejar a esa persona sin poder entrar (no vería la contraseña nueva, que llega al
correo del dueño, pero la vieja dejaría de funcionar). El captcha y el rate limit solo lo
frenan.

Solución, sin salirse de lo que pide la issue:

- La contraseña autogenerada se guarda como **pendiente** (`reset_hash`, caduca en 1 hora) y
  se envía por correo.
- La contraseña actual sigue funcionando.
- Al entrar con la pendiente, pasa a ser la contraseña del usuario y la vieja deja de valer.
- Si el usuario entra con su contraseña de siempre, la pendiente se descarta (se acordaba).

Así un reseteo malintencionado solo produce un correo que el dueño puede ignorar.

## Diseño

### Base de datos: migraciones

El repo solo tenía scripts de init (`db/init/`), que Postgres ejecuta una única vez con el
volumen vacío. Para añadir columnas a una bbdd que ya existe sin borrarla se introducen
migraciones mínimas:

- `api/migrations/NNN_nombre.sql`: SQL idempotente, en orden alfabético.
- `api/app/migrations.py`: al arrancar la API, crea `migraciones_aplicadas(nombre, aplicada_en)`
  si no existe y aplica, cada una en su transacción, las que falten. Después, si
  `APP_ADMIN_EMAIL` está definido, rellena el email del admin si aún no tiene.
- Si la bbdd no responde al arrancar, la API falla con un mensaje claro en el log
  (`depends_on: service_healthy` hace que no ocurra en un arranque normal).
- `db/init/` no se toca. Si el esquema crece, se cambia a Alembic.

`001_reseteo_y_captcha.sql`:

```sql
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS email        VARCHAR(255);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS reset_hash   VARCHAR(255);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS reset_expira TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS captchas_usados (firma TEXT PRIMARY KEY, expira TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS intentos_reset (
  id SERIAL PRIMARY KEY, clave TEXT NOT NULL, creado_en TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS intentos_reset_clave_fecha ON intentos_reset (clave, creado_en);
```

El estado del captcha (retos usados) y del rate limit se guarda en bbdd y no en memoria de la
API: sobrevive a reinicios y vale aunque haya varias copias de la API.

### API

| Endpoint | Entrada | Respuestas |
|---|---|---|
| `GET /api/captcha` | — | 200 reto ALTCHA (caduca en 5 min) |
| `POST /api/auth/login` | `username`, `password`, `altcha` | 200 / 400 captcha / 401 / 503 |
| `POST /api/auth/reset` | `username`, `altcha` | 202 mensaje genérico / 400 captcha / 429 |

- **Captcha** (`app/captcha.py`): `create_challenge` con `ALTCHA_HMAC_KEY` y caducidad de 5 min;
  la verificación comprueba la firma y la caducidad, y luego inserta la firma del reto en
  `captchas_usados` (`ON CONFLICT DO NOTHING`): si no se inserta, es un reenvío y se rechaza.
  En cada inserción se borran los caducados. Error: 400 «Verificación anti-bot no válida».
  Con `ALTCHA_ENABLED=false` no se verifica y la API lo avisa en el log al arrancar.
- **Login**: comprueba captcha → contraseña actual (si vale, borra la pendiente) → si no, la
  pendiente no caducada (si vale, la promueve). Mismo 401 que antes en cualquier otro caso.
- **Reseteo**, en este orden:
  1. Captcha (400 si falla).
  2. Rate limit: si en la última hora hay ≥ `RESET_MAX_POR_HORA` (5) intentos de esa IP o de
     ese usuario → 429 «Demasiados intentos. Prueba más tarde.». Se elige 429 en vez del
     mensaje genérico porque no revela nada (afecta igual a usuarios que existen y que no) y
     el usuario legítimo necesita saber que debe esperar.
  3. Se apunta el intento (IP y usuario).
  4. Si el usuario existe y tiene email: transacción → guarda `reset_hash` (bcrypt, el mismo
     `hash_password` que el resto) y `reset_expira = now() + 1 h` → envía el correo → commit.
     Si el envío falla: rollback y error en el log del servidor.
  5. Siempre 202 «Si el usuario existe, recibirá un correo con una contraseña nueva.»: igual
     para inexistente, sin email, válido o fallo de correo, para no revelar qué usuarios hay.
- La contraseña nueva se genera con `secrets.token_urlsafe(12)`.
- Los endpoints siguen siendo `def` (síncronos): FastAPI los ejecuta en un threadpool, así que
  el envío SMTP no bloquea el event loop.

### Correo (`app/mailer.py`, `smtplib` de la librería estándar)

- `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`,
  `SMTP_TLS` = `starttls` (defecto; Gmail/Outlook en 587) | `ssl` (465) | `none`, timeout 10 s.
- **Modo log**: si `SMTP_HOST` está vacío, el correo (con la contraseña en claro) se escribe en
  `docker compose logs web`. Solo para desarrollo; el README lo advierte.

### Configuración (`.env`, `.env.example`, tabla del README)

Nuevas: `APP_ADMIN_EMAIL`, `SMTP_*`, `SMTP_TLS`, `ALTCHA_HMAC_KEY` (≥ 32 caracteres, obligatoria
si el captcha está activo), `ALTCHA_ENABLED` (defecto `true`), `RESET_MAX_POR_HORA` (defecto 5).

### Frontend

- `components/Captcha.tsx`: envuelve el web component `altcha-widget` (`challengeurl=/api/captcha`)
  y avisa con el payload al resolverse. Para reiniciarlo con un reto nuevo, el padre cambia su
  `key`.
- `components/Logo.tsx`: el logo, usado solo por `Login` y `ResetPassword`.
- `Login.tsx`: logo, captcha (el botón exige captcha resuelto), enlace a `/reset-password`,
  reinicio del captcha tras cada fallo.
- `pages/ResetPassword.tsx`: usuario + captcha, mensaje genérico o error, enlace de vuelta al
  login, reinicio del captcha tras cada envío.
- `client.ts`: `login(username, password, altcha)` y `resetPassword(username, altcha)`.
- `App.tsx`: ruta `/reset-password` (sin sesión; con sesión redirige a `/`).

### Linter

- API: `ruff` en `requirements-dev.txt`, configuración en `api/pyproject.toml`
  (`ruff check .`). Si salta algo en el código existente, va en un commit aparte.
- Frontend: el `oxlint` que ya existe (`npm run lint`).

## Tests

**pytest** (un doble de bbdd como hasta ahora; fixture que genera un payload ALTCHA válido
resolviendo el reto con la propia librería):

- Login con captcha válido entra; los tests de login existentes siguen en verde.
- Captcha ausente, inválido, caducado o reutilizado → 400.
- Reseteo: usuario válido → 202, correo enviado, `reset_hash` bcrypt verificable con
  `verify_password`.
- Tras el reseteo la vieja sigue valiendo; tras entrar con la nueva, la vieja ya no.
- Entrar con la vieja descarta la pendiente; una pendiente caducada no vale.
- Misma respuesta y código para inexistente, sin email, válido y fallo de correo; con el
  fallo, rollback (no queda `reset_hash`).
- Rate limit: el intento N+1 por usuario o por IP → 429.
- Mailer: modo log escribe en el log; STARTTLS / SSL / none llaman a lo esperado de `smtplib`
  (mockeado), con timeout.
- Migraciones: se aplican las pendientes una vez y se rellena el email del admin.
- Config: `ALTCHA_HMAC_KEY` obligatoria y ≥ 32 si el captcha está activo.

**Vitest**:

- El logo aparece en login y en reseteo, y no en home.
- «¿Olvidaste tu contraseña?» navega a `/reset-password`.
- El login envía el payload del captcha; tras un fallo se pide un reto nuevo (el widget se
  vuelve a montar).
- La página de reseteo envía usuario + captcha y muestra el mensaje genérico.

## Fuera de alcance

- Enlace de un solo uso para elegir contraseña (alternativa más estándar al correo con
  contraseña; la pendiente ya resuelve el riesgo principal).
- Rate limit del login (el captcha lo frena) y la diferencia de tiempos de P5.
- HTTPS / cookie `Secure`.

## Commits previstos (`feat: … (Refs #4)`, uno por bloque)

1. `chore: añade ruff a la API` (+ arreglos de ruff en código existente, si los hay).
2. `chore: quita referencias personales de comentarios del compose y del Dockerfile de db`.
3. `feat: migraciones de bbdd al arrancar la API (Refs #4)`.
4. `feat: captcha ALTCHA en login (Refs #4)`.
5. `feat: envío de correo por SMTP o log (Refs #4)`.
6. `feat: reseteo de contraseña con contraseña pendiente y rate limit (Refs #4)`.
7. `feat: logo, captcha y pantalla de reseteo en el frontend (Refs #4)`.
8. `docs: README con variables y funcionamiento del reseteo y el captcha (Refs #4)`.
