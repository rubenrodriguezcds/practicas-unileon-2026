# practicas-unileon-2026
Proyecto I+D para diseñar y desarrollar un gestor documental

Primera entrega: el entorno en dos contenedores Docker con una aplicación web mínima
(login y home con logout) cuyo usuario vive en la base de datos.

## Arquitectura

```
 Navegador ──:80──►  [ web ]  ──red interna de compose (db:5432)──►  [ db ]
                     React + Vite (compilado)                         PostgreSQL 16
                     FastAPI  /api/*                                   + servidor SSH
                                                     DBeaver/psql ──:1521──► Postgres
                                                     ssh          ──:22────► SSH
```

| Contenedor | Contenido | Puertos publicados |
|---|---|---|
| `db` | PostgreSQL 16 + OpenSSH. Al arrancar crea las tablas si no existen. | `1521` → 5432 (Postgres), `22` (SSH) |
| `web` | FastAPI sirve la API (`/api/*`) y el frontend React compilado. | `80` |

Ningún otro puerto queda expuesto. La web llega a la bbdd por la red interna de Docker
(`db:5432`), que no es accesible desde fuera.

## Puesta en marcha

Requisitos: [Docker Desktop](https://www.docker.com/products/docker-desktop/) (o Docker Engine + Compose v2).

```bash
git clone https://github.com/rubenrodriguezcds/practicas-unileon-2026.git
cd practicas-unileon-2026
cp .env.example .env          # y cambia los valores (ver abajo)
docker compose up -d --build
docker compose ps             # db (healthy) y web (Up)
```

Abre **http://localhost** (puerto 80, el de la web por defecto) e inicia sesión con el
usuario `admin` y la contraseña que pusiste en `APP_ADMIN_PASSWORD`.

### Variables de entorno (`.env`)

| Variable | Para qué |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Base de datos y credenciales de Postgres (las usan `db` y `web`) |
| `SSH_USER`, `SSH_PASSWORD` | Usuario para entrar por SSH al contenedor `db` |
| `APP_ADMIN_PASSWORD` | Contraseña del usuario `admin` de la aplicación web. Se crea al inicializar la bbdd: para cambiarla después hay que recrearla (`docker compose down -v`) |
| `APP_SECRET` | Firma de la cookie de sesión. **Mínimo 32 caracteres** o la web no arranca. Genera uno con `python -c "import secrets;print(secrets.token_hex(32))"` |

El `.env` no se sube nunca al repositorio.

## Uso

| Qué | Cómo |
|---|---|
| Aplicación web | http://localhost |
| Estado de la API | http://localhost/api/health |
| Documentación de la API | http://localhost/api/docs |
| Postgres desde el host | `psql -h localhost -p 1521 -U gestor gestor` (o DBeaver con host `localhost`, puerto `1521`) |
| SSH al contenedor de bbdd | `ssh -p 22 <SSH_USER>@localhost` |
| Ver logs | `docker compose logs -f web` / `docker compose logs -f db` |
| Parar (conserva los datos) | `docker compose down` |
| Parar y borrar la bbdd | `docker compose down -v` (al volver a arrancar se recrean las tablas) |

### API

| Método y ruta | Respuesta |
|---|---|
| `POST /api/auth/login` `{"username","password"}` | 200 `{"username"}` + cookie de sesión · 401 si las credenciales no son válidas |
| `POST /api/auth/logout` | 204 |
| `GET /api/auth/me` | 200 `{"username"}` · 401 sin sesión |
| `GET /api/health` | 200 `{"status":"ok"}` |

Si la base de datos no está disponible, la API responde 503.

## Cómo funciona por dentro

- **Creación del modelo de datos**: los scripts de `db/init/` se ejecutan automáticamente
  la primera vez que arranca el contenedor (con el volumen vacío). Además son idempotentes
  (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), así que relanzarlos no rompe nada.
- **Datos persistentes** en el volumen `pgdata`: sobreviven a `docker compose down`.
- **Orden de arranque**: `web` espera a que `db` pase su *healthcheck* (`pg_isready`).
- **Contraseñas** guardadas con hash bcrypt; nunca en claro.
- **Sesión** en una cookie firmada `HttpOnly` (el JavaScript de la página no puede leerla).
- **Imagen web** en dos etapas: Node compila el frontend y la imagen final solo lleva
  Python, la API y los estáticos. Se ejecuta sin usuario root.

## Estructura

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
  app/db.py               Conexión a Postgres
  app/security.py         Hash y verificación de contraseñas
  app/routers/auth.py     Login, logout y sesión
  app/spa.py              Sirve el frontend compilado
  app/main.py             Monta la aplicación
  tests/
frontend/                 Frontend React + Vite + TypeScript
  src/api/client.ts       Único punto de llamada a la API
  src/pages/              Login y Home
  src/App.tsx             Rutas y control de sesión
docker/web.Dockerfile     Imagen del contenedor web
```

El frontend solo llama a rutas relativas `/api/...` y la API no depende del frontend, de
modo que más adelante se puede separar en tres contenedores (frontend con nginx, API y
bbdd) cambiando solo los Dockerfiles y el compose.

## Desarrollo y tests

```bash
# API
cd api
python -m venv .venv
.venv/Scripts/activate        # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements-dev.txt
pytest -q

# Frontend
cd frontend
npm ci
npm test
npm run dev                   # http://localhost:5173, redirige /api a localhost:8000
```

Para desarrollar el frontend contra la API local: `uvicorn app.main:app --port 8000` dentro
de `api/` (con las variables de `.env` cargadas y una bbdd accesible).

## Problemas frecuentes

- **El puerto 80 o el 22 ya está en uso** (IIS, OpenSSH Server de Windows…): compruébalo con
  `netstat -ano | findstr :80` o `:22` y para ese servicio, o cambia el puerto de la
  izquierda en `docker-compose.yml` (p. ej. `"2222:22"`).
- **El login falla en `http://localhost:5173`**: ese es el servidor de desarrollo de Vite
  (`npm run dev`) y necesita la API arrancada aparte en el puerto 8000. La aplicación de
  Docker está en `http://localhost`.
- **La web no arranca y en el log aparece `app_secret`**: el `APP_SECRET` del `.env` tiene
  menos de 32 caracteres.
- **Cambié `APP_ADMIN_PASSWORD` o los scripts de `db/init/` y no se aplican**: solo se ejecutan con el volumen vacío;
  usa `docker compose down -v` (borra los datos).

## Equipo

- Sergio Martínez — contenedor web (API y frontend)
- Mario Costello— contenedor de base de datos y docker-compose

Tutor: Rubén Rodriguez.
