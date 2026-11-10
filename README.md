<div align="center">

# practicas-unileon-2026

**Proyecto I+D para diseñar y desarrollar un gestor documental**

![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)

[Arquitectura](#arquitectura) · [Puesta en marcha](#puesta-en-marcha) · [Uso](#uso) · [API](#api) · [Cómo funciona](#cómo-funciona-por-dentro) · [Desarrollo](#desarrollo-y-tests) · [Problemas](#problemas-frecuentes)

</div>

---

> [!NOTE]
> **Primera entrega:** el entorno en dos contenedores Docker con una aplicación web mínima
> (login y home con logout) cuyo usuario vive en la base de datos.
>
> **Issue #4:** logo en el login, recuperación de contraseña por correo y captcha anti-bot.
>
> **Issue #5:** menú de la aplicación y gestión de roles, solo para el administrador.
>
> **Issue #7:** gestión de proyectos y de sus documentos adjuntos, solo para el administrador.

## Arquitectura

```mermaid
flowchart LR
    nav(["Navegador"])
    clientebd(["Cliente de bbdd"])
    sshc(["Cliente SSH"])

    subgraph docker["Docker Compose · red interna"]
        direction LR
        subgraph web["web"]
            spa["React compilado"]
            api["FastAPI · /api/*"]
        end
        subgraph db["db"]
            pg[("PostgreSQL 16")]
            sshd["OpenSSH"]
        end
        api -- "db:5432" --> pg
    end

    nav -- ":80" --> web
    clientebd -- ":1521" --> pg
    sshc -- ":22" --> sshd

    classDef webC fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef dbC fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef ext fill:#fef3c7,stroke:#d97706,color:#78350f
    class spa,api webC
    class pg,sshd dbC
    class nav,clientebd,sshc ext
```

| Contenedor | Contenido | Puertos publicados |
|---|---|---|
| `web` | FastAPI sirve la API (`/api/*`) y el frontend React compilado. | `80` |
| `db` | PostgreSQL 16 + OpenSSH. Al arrancar crea las tablas si no existen. | `1521` → 5432 (Postgres), `22` (SSH) |

> [!IMPORTANT]
> Ningún otro puerto queda expuesto. La web llega a la bbdd por la **red interna** de Docker
> (`db:5432`), que no es accesible desde fuera.

## Puesta en marcha

**Requisitos:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (o Docker Engine + Compose v2).

```bash
git clone https://github.com/rubenrodriguezcds/practicas-unileon-2026.git
cd practicas-unileon-2026
cp .env.example .env          # y cambia los valores (ver abajo)
docker compose up -d --build
docker compose ps             # db (healthy) y web (Up)
```

> [!TIP]
> Abre **http://localhost/login** (puerto 80, el de la web por defecto) e inicia sesión con el
> usuario `admin` y la contraseña que pusiste en `APP_ADMIN_PASSWORD`.

### Variables de entorno (`.env`)

| Variable | Para qué |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Base de datos y credenciales de Postgres (las usan `db` y `web`) |
| `SSH_USER`, `SSH_PASSWORD` | Usuario para entrar por SSH al contenedor `db` |
| `APP_ADMIN_PASSWORD` | Contraseña del usuario `admin` de la aplicación web. Se crea al inicializar la bbdd: para cambiarla después hay que recrearla (`docker compose down -v`) |
| `APP_SECRET` | Firma de la cookie de sesión. **Mínimo 32 caracteres** o la web no arranca |
| `APP_ADMIN_EMAIL` | Email del `admin`, a donde llega su contraseña nueva si la resetea. La API se lo pone al arrancar si aún no tiene |
| `ALTCHA_HMAC_KEY` | Clave con la que la API firma los retos del captcha. **Mínimo 32 caracteres** o la web no arranca |
| `ALTCHA_ENABLED` | `false` desactiva el captcha (solo tests o desarrollo; la API lo avisa en el log). Por defecto `true` |
| `RESET_MAX_POR_HORA` | Reseteos de contraseña permitidos por hora, por usuario y por IP. Por defecto `5` |
| `DOCUMENTO_MAX_MB` | Tamaño máximo de cada documento adjunto a un proyecto, en MB. Por defecto `50` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Servidor de correo para el reseteo. **Vacío = modo log** (ver aviso abajo) |
| `SMTP_TLS` | `starttls` (puerto 587, Brevo y Gmail; por defecto), `ssl` (465) o `none` |

Para generar un `APP_SECRET` o un `ALTCHA_HMAC_KEY`:

```bash
python -c "import secrets;print(secrets.token_hex(32))"
```

> [!CAUTION]
> El `.env` contiene secretos y **no se sube nunca** al repositorio (está en `.gitignore`).

> [!WARNING]
> **Modo log del correo, solo para desarrollo.** Con `SMTP_HOST` vacío los correos no se
> envían: se escriben en `docker compose logs web` **con la contraseña nueva en claro**. En
> cualquier entorno compartido hay que configurar un servidor SMTP. El proyecto usa
> [Brevo](https://www.brevo.com) (gratis, sin dominio propio): `SMTP_HOST=smtp-relay.brevo.com`,
> `SMTP_PORT=587`, `SMTP_TLS=starttls`, el login y la clave SMTP de Brevo en `SMTP_USER` y
> `SMTP_PASSWORD`, y en `SMTP_FROM` el remitente verificado en Brevo. Gmail con contraseña de
> aplicación también funciona; Outlook.com personal no (Microsoft exige OAuth2).

> [!NOTE]
> El captcha ([ALTCHA](https://altcha.org)) es open source y lo sirve la propia API: **no
> necesita ninguna cuenta externa** (ni Google ni Cloudflare), solo la clave `ALTCHA_HMAC_KEY`.

## Uso

| Qué | Cómo |
|---|---|
| Aplicación web | http://localhost/login |
| Recuperar contraseña | http://localhost/reset-password (o «¿Olvidaste tu contraseña?» en el login) |
| Gestión de roles (solo administrador) | http://localhost/roles (o «Roles» en el menú) |
| Gestión de proyectos y documentos (solo administrador) | http://localhost/proyectos (o «Proyectos» en el menú) |
| Estado de la API | http://localhost/api/health |
| Documentación de la API | http://localhost/api/docs |
| Consultar la bbdd | `docker compose exec db psql -U gestor -d gestor` (ya incluido), o cualquier cliente de PostgreSQL (DBeaver, pgAdmin…) con host `localhost` y puerto `1521` |
| SSH al contenedor de bbdd | `ssh -p 22 <SSH_USER>@localhost` |
| Ver logs | `docker compose logs -f web` / `docker compose logs -f db` |
| Parar (conserva los datos) | `docker compose down` |
| Parar y borrar la bbdd | `docker compose down -v` (al volver a arrancar se recrean las tablas) |

## API

| Método | Ruta | Respuesta |
|---|---|---|
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/api/auth/login` `{"username","password","altcha"}` | 200 `{"username","es_admin"}` + cookie de sesión · 400 captcha no válido · 401 si las credenciales no son válidas |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/api/auth/reset` `{"username","altcha"}` | 202 siempre con el mismo mensaje · 400 captcha no válido · 429 demasiados intentos |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/captcha` | 200 reto del captcha (caduca en 5 minutos) |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/api/auth/logout` | 204 |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/auth/me` | 200 `{"username","es_admin"}` · 401 sin sesión |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/health` | 200 `{"status":"ok"}` |

**Roles** (solo administrador: 401 sin sesión, **403** si el usuario no es administrador):

| Método | Ruta | Respuesta |
|---|---|---|
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/roles` | 200 lista de roles por nombre, con `num_usuarios` |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/api/roles` `{"nombre","descripcion"}` | 201 rol creado · 409 nombre repetido |
| ![PUT](https://img.shields.io/badge/PUT-fca130?style=flat-square) | `/api/roles/{id}` `{"nombre","descripcion"}` | 200 rol editado · 404 · 409 nombre repetido |
| ![DELETE](https://img.shields.io/badge/DELETE-f93e3e?style=flat-square) | `/api/roles/{id}` | 204 · 404 · 409 si algún usuario tiene el rol |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/roles/{id}/usuarios` | 200 usuarios que tienen el rol · 404 |

**Proyectos y documentos** (solo administrador: 401 sin sesión, **403** si el usuario no es administrador):

| Método | Ruta | Respuesta |
|---|---|---|
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/proyectos` | 200 lista de proyectos por nombre, con `num_documentos` |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/api/proyectos` `{"nombre","tipo","descripcion"}` | 201 proyecto creado · 409 nombre repetido |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/proyectos/{id}` | 200 proyecto con sus documentos (`id`, `nombre`, `tamano`, `visible`) · 404 |
| ![DELETE](https://img.shields.io/badge/DELETE-f93e3e?style=flat-square) | `/api/proyectos/{id}` | 204 (borra también sus documentos) · 404 |
| ![POST](https://img.shields.io/badge/POST-49cc90?style=flat-square) | `/api/proyectos/{id}/documentos` (multipart, campo `archivo`) | 201 documento · 404 · 409 nombre repetido · 413 demasiado grande · 415 tipo no permitido · 422 vacío |
| ![GET](https://img.shields.io/badge/GET-61affe?style=flat-square) | `/api/documentos/{id}` (`?ver=1` para abrirlo en el navegador) | 200 el archivo · 404 |
| ![DELETE](https://img.shields.io/badge/DELETE-f93e3e?style=flat-square) | `/api/documentos/{id}` | 204 · 404 |

> [!WARNING]
> Si la base de datos no está disponible, la API responde **503** «Base de datos no disponible».

<details>
<summary><b>Flujo de inicio de sesión, paso a paso</b></summary>

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant F as React
    participant A as FastAPI
    participant D as PostgreSQL

    U->>F: Abre http://localhost/login
    F->>A: GET /api/auth/me
    A-->>F: 401 (sin sesión)
    F-->>U: Pantalla de login
    U->>F: admin + contraseña + «No soy un robot»
    F->>A: GET /api/captcha
    A-->>F: reto firmado
    F->>F: resuelve el reto (~1 s)
    F->>A: POST /api/auth/login (con la solución)
    A->>D: apunta el reto como usado
    A->>D: SELECT password_hash FROM usuarios
    D-->>A: hash bcrypt
    A->>A: verifica la contraseña
    A-->>F: 200 + cookie HttpOnly
    F-->>U: «Hola, admin»
```

</details>

<details>
<summary><b>Recuperar la contraseña: cómo funciona y por qué así</b></summary>

1. El usuario escribe su nombre, resuelve el captcha y pulsa «Enviar contraseña nueva».
2. La API genera una contraseña aleatoria, la guarda con hash bcrypt como **pendiente** (vale
   1 hora) y la envía al email del usuario. Solo si el correo sale, se confirma en la bbdd.
3. La contraseña de siempre **sigue funcionando**. Al entrar con la nueva, la nueva pasa a ser
   la contraseña y la vieja deja de valer. Si entra con la vieja, la pendiente se descarta.

Por qué así:

- **Nadie puede dejar sin acceso a otro.** Si la contraseña cambiara al pedir el reseteo,
  bastaría saber un nombre de usuario para bloquearlo. Así, un reseteo que no pidió el dueño
  solo le genera un correo que puede ignorar.
- **No revela qué usuarios existen.** La respuesta es siempre la misma (exista o no el usuario,
  tenga o no email, falle o no el correo). Los fallos de correo quedan en el log del servidor.
- **Límite de intentos** por usuario y por IP (`RESET_MAX_POR_HORA`). Al superarlo responde 429.
- **Captcha** en el login y en el reseteo. Cada reto caduca a los 5 minutos y vale una sola vez.

</details>

<details>
<summary><b>Gestión de roles: cómo funciona y por qué así</b></summary>

- **Quién es administrador** lo dice la columna `usuarios.es_admin` (por defecto `false`; el
  `admin` del seed la tiene a `true`).
- **Solo el administrador** ve la entrada «Roles» del menú. Esconderla es solo comodidad: quien
  protege es la API, que comprueba `es_admin` **en la bbdd en cada petición** y responde 403 si no
  lo es. Así, quitar el permiso a alguien surte efecto en su siguiente petición.
- **Un usuario puede tener varios roles** (tabla `usuario_roles`).
- **El nombre del rol es único**: dos roles con el mismo nombre serían indistinguibles.
- **Un rol que tienen usuarios no se puede borrar** (409, indicando cuántos): borrarlo les quitaría
  el rol sin avisar. La bbdd también lo impide (`ON DELETE RESTRICT`).
- **Asignar roles a usuarios** todavía no tiene pantalla (la issue solo pide ver quién los tiene):
  ver «¿Cómo asigno un rol a un usuario?» en Problemas frecuentes.

</details>

<details>
<summary><b>Gestión de proyectos y documentos: cómo funciona y por qué así</b></summary>

- **Solo el administrador**, igual que roles: la API responde 403 a cualquier otro.
- **El nombre del proyecto es único sin distinguir mayúsculas** («Web» y «web» chocan). Nombre,
  tipo y descripción no se editan después de crearlo: la edición solo añade y borra documentos.
- **Borrar un proyecto borra todos sus documentos** (la bbdd lo hace sola, `ON DELETE CASCADE`).
  La pantalla avisa antes de cuántos documentos se van a borrar.
- **Los documentos se guardan dentro de Postgres** (columna `BYTEA`, el «blob» de Postgres): un
  fichero entero tal cual. Por eso hay un tamaño máximo por documento (`DOCUMENTO_MAX_MB`, 50 MB).
  Una subida que anuncia más tamaño se corta antes de leerla, para no llenar el disco.
- **Solo se admiten algunos tipos**: PDF, imágenes (`png`, `jpg`, `jpeg`, `gif`, `webp`), texto
  (`txt`, `md`, `csv`) y Office/LibreOffice (`doc`, `docx`, `xls`, `xlsx`, `ppt`, `pptx`, `odt`,
  `ods`, `odp`). El resto (`html`, `svg`, ejecutables…) se rechaza con 415.
- **«Ver» solo abre en el navegador PDF, imágenes y texto**; lo demás se descarga. Las descargas
  llevan cabeceras que impiden que un documento ejecute código con la sesión del administrador.
- **En un mismo proyecto no puede haber dos documentos con el mismo nombre** (con la extensión y
  sin distinguir mayúsculas): `informe.pdf` e `informe.docx` pueden convivir.
- **Se pueden arrastrar varios archivos a la vez**: cada uno se sube por separado y muestra su
  estado, así que si uno falla los demás suben igual.

</details>

## Cómo funciona por dentro

- **Creación del modelo de datos**: los scripts de `db/init/` se ejecutan automáticamente
  la primera vez que arranca el contenedor (con el volumen vacío). Además son idempotentes
  (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), así que relanzarlos no rompe nada.
- **Migraciones**: los scripts de `db/init/` solo crean la bbdd desde cero. Para cambiar el
  esquema de una bbdd que ya tiene datos (añadir una columna, una tabla…) se añade un fichero
  `api/migrations/NNN_nombre.sql`. La API aplica al arrancar los que falten, en orden, y los
  apunta en la tabla `migraciones_aplicadas`. Así nadie tiene que borrar la bbdd para actualizar.
- **Datos persistentes** en el volumen `pgdata`: sobreviven a `docker compose down`.
- **Orden de arranque**: `web` espera a que `db` pase su *healthcheck* (`pg_isready`).
- **Contraseñas** guardadas con hash bcrypt; nunca en claro.
- **Sesión** en una cookie firmada `HttpOnly` (el JavaScript de la página no puede leerla).
- **Imagen web** en dos etapas: Node compila el frontend y la imagen final solo lleva
  Python, la API y los estáticos. Se ejecuta sin usuario root.

<details>
<summary><b>Estructura del repositorio</b></summary>

```
docker-compose.yml        Orquesta db + web
.env.example              Plantilla de variables
db/                       Contenedor de base de datos
  Dockerfile              postgres:16 + openssh-server
  entrypoint.sh           Arranca sshd y luego el arranque oficial de Postgres
  init/01_schema.sql      Tablas
  init/02_seed.sh         Usuario admin de la web (contraseña del .env)
api/                      Backend FastAPI
  app/config.py           Configuración desde variables de entorno
  app/db.py               Conexión a Postgres y consultas
  app/migrations.py       Aplica las migraciones pendientes al arrancar
  app/security.py         Hash y verificación de contraseñas
  app/deps.py             Permisos: exige sesión de administrador
  app/captcha.py          Retos y verificación del captcha ALTCHA
  app/mailer.py           Envío de correo (SMTP o log)
  app/routers/auth.py     Login, logout, sesión y reseteo de contraseña
  app/routers/captcha.py  Entrega retos del captcha
  app/routers/roles.py    Gestión de roles (solo administrador)
  app/routers/proyectos.py  Gestión de proyectos y documentos (solo administrador)
  app/documentos.py       Tipos de archivo permitidos y nombres de los documentos
  app/spa.py              Sirve el frontend compilado
  app/main.py             Monta la aplicación
  migrations/             Cambios de esquema (NNN_nombre.sql)
  tests/
frontend/                 Frontend React + Vite + TypeScript
  src/api/client.ts       Único punto de llamada a la API
  src/pages/              Login, ResetPassword, Home y Roles
                          Proyectos y ProyectoDetalle (gestión de proyectos y documentos)
  src/components/         Captcha, Logo y Layout (menú de las pantallas con sesión)
                          ConfirmDialog (aviso antes de borrar) y DropZone (arrastrar archivos)
  src/App.tsx             Rutas y control de sesión
docker/web.Dockerfile     Imagen del contenedor web
```

</details>

> [!NOTE]
> El frontend solo llama a rutas relativas `/api/...` y la API no depende del frontend, de
> modo que más adelante se puede separar en **tres contenedores** (frontend con nginx, API y
> bbdd) cambiando solo los Dockerfiles y el compose.

## Desarrollo y tests

<details>
<summary><b>API (FastAPI)</b></summary>

```bash
cd api
python -m venv .venv
.venv/Scripts/activate        # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements-dev.txt
pytest -q
ruff check .                  # linter
```

Para levantar la API en local: `uvicorn app.main:app --port 8000` dentro de `api/` (con las
variables de `.env` cargadas y una bbdd accesible).

</details>

<details>
<summary><b>Frontend (React + Vite)</b></summary>

```bash
cd frontend
npm ci
npm test
npm run lint
npm run dev                   # http://localhost:5173, redirige /api a localhost:8000
```

</details>

## Problemas frecuentes

<details>
<summary><b>Docker arranca pero el login con <code>admin</code> dice «Usuario o contraseña incorrectos»</b></summary>

El usuario `admin` se crea **solo la primera vez**, cuando la base de datos está vacía. Si la
bbdd ya existía de antes (otra versión del seed u otra `APP_ADMIN_PASSWORD`), conserva la
contraseña antigua. Recréala (borra los datos):

```bash
docker compose down -v
docker compose up -d --build
```

Para comprobar qué hay: `docker compose logs db | grep 02_seed` debe mostrar que se ejecutó
`02_seed.sh`, y comprueba que entras por **http://localhost/login** (no por `:5173`).

</details>

<details>
<summary><b>El puerto 80 o el 22 ya está en uso</b></summary>

Suele ser IIS o el OpenSSH Server de Windows. Compruébalo con `netstat -ano | findstr :80`
(o `:22`) y para ese servicio, o cambia el puerto de la izquierda en `docker-compose.yml`
(p. ej. `"2222:22"`).

</details>

<details>
<summary><b>El login falla en <code>http://localhost:5173</code></b></summary>

Ese es el servidor de desarrollo de Vite (`npm run dev`) y necesita la API arrancada aparte
en el puerto 8000. La aplicación de Docker está en **http://localhost/login**.

</details>

<details>
<summary><b>El contenedor <code>web</code> no arranca (o se para nada más arrancar)</b></summary>

Mira el motivo con `docker compose logs web --tail 30` y `docker compose logs db --tail 30`:

- **`app_secret` … `at least 32 characters`**: el `APP_SECRET` del `.env` es demasiado corto.
  El de `.env.example` (`cambia-esto`) lo es a propósito, para que nadie use un secreto
  conocido. Genera uno con `python -c "import secrets;print(secrets.token_hex(32))"`.
- **`ALTCHA_HMAC_KEY debe tener al menos 32 caracteres`**: falta la clave del captcha en el
  `.env` (pasa al actualizar desde una versión anterior). Genérala igual que `APP_SECRET`.
- **`Falta APP_ADMIN_PASSWORD en el .env`** (en el log de `db`): sin esa variable la bbdd no
  arranca, y `web` espera a que `db` esté sana. Añádela y haz `docker compose down -v` y `up`.
- **`port is already allocated`**: otra cosa usa el puerto 80 (ver «El puerto 80 o el 22 ya está en uso»).

</details>

<details>
<summary><b>Cambié <code>APP_ADMIN_PASSWORD</code> o los scripts de <code>db/init/</code> y no se aplican</b></summary>

Solo se ejecutan con el volumen vacío; usa `docker compose down -v` (borra los datos). Para
cambiar el esquema sin borrar datos, añade una migración en `api/migrations/`.

</details>

<details>
<summary><b>He pedido una contraseña nueva y no me llega el correo</b></summary>

- Sin `SMTP_HOST` en el `.env` no se envía nada: el correo está en `docker compose logs web`.
- Con SMTP configurado, si el envío falla el error aparece en `docker compose logs web` y la
  contraseña no cambia (a propósito, la página muestra el mismo mensaje que si hubiera ido bien).
- El usuario necesita un email en la bbdd: el `admin` lo toma de `APP_ADMIN_EMAIL`.

</details>

<details>
<summary><b>¿Cómo asigno un rol a un usuario, o hago administrador a otro?</b></summary>

De momento no hay pantalla para esto (la gestión de usuarios es otra issue). Desde `psql`
(`docker compose exec db psql -U gestor -d gestor`):

```sql
-- Dar el rol 'Tutor' al usuario 'pepe' (el rol se crea antes en http://localhost/roles)
INSERT INTO usuario_roles (usuario_id, rol_id)
SELECT u.id, r.id FROM usuarios u, roles r WHERE u.username = 'pepe' AND r.nombre = 'Tutor';

-- Quitárselo
DELETE FROM usuario_roles
WHERE usuario_id = (SELECT id FROM usuarios WHERE username = 'pepe')
  AND rol_id = (SELECT id FROM roles WHERE nombre = 'Tutor');

-- Hacer administrador a 'pepe' (o quitárselo con false)
UPDATE usuarios SET es_admin = true WHERE username = 'pepe';
```

</details>

<details>
<summary><b>No veo «Roles» en el menú</b></summary>

Solo aparece al administrador (`usuarios.es_admin = true`). Si acabas de cambiarlo en la bbdd,
recarga la página.

</details>

## Equipo

| Persona | Parte |
|---|---|
| Sergio Martínez | Contenedor web (API y frontend) |
| Mario Costello | Contenedor de base de datos, docker-compose y gestión de roles |
| Rubén Rodriguez | Tutor |
