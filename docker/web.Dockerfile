# Imagen del contenedor `web`: frontend React compilado + API FastAPI en el puerto 80.
#
# Para qué: producir una imagen que, al arrancar, sirve la página web y la API desde el mismo
# sitio (http://localhost), sin necesitar Node ni las fuentes de React dentro.
#
# Cómo (dos etapas):
#   1. Una imagen de Node instala dependencias y compila React (`npm run build` → dist/).
#   2. La imagen final, solo Python, recibe la API y el dist/ ya compilado. Node se descarta,
#      así que la imagen final es más pequeña y tiene menos superficie de ataque.
#
# Por qué está en docker/ y no en api/ ni en frontend/: necesita las dos carpetas, así que se
# construye desde la raíz del repo (contexto «.»), como indica docker-compose.yml.
#
# Para separar en el futuro en 3 contenedores: frontend/Dockerfile (nginx) y api/Dockerfile;
# este fichero dejaría de usarse sin cambiar código.

# Etapa 1: compila el frontend. Node solo hace falta aquí; no llega a la imagen final.
# node:22 porque Vite 8 exige Node >= 20.19.
FROM node:22-slim AS frontend
WORKDIR /frontend
# Primero solo las dependencias: si no cambian, Docker reutiliza esta capa y no repite npm ci.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Etapa 2: imagen final con Python, la API y los estáticos del frontend.
FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app ./app
COPY --from=frontend /frontend/dist ./static
# STATIC_DIR activa que la API sirva el frontend; sin ella, la API funciona sola (útil al separar en 3 contenedores).
ENV STATIC_DIR=/app/static PYTHONUNBUFFERED=1
EXPOSE 80
# Sin root: Docker permite a cualquier usuario del contenedor escuchar en el 80.
RUN useradd --system --no-create-home app
USER app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","80"]
