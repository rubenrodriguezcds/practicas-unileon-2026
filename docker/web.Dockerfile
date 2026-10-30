FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app ./app
COPY --from=frontend /frontend/dist ./static
ENV STATIC_DIR=/app/static PYTHONUNBUFFERED=1
EXPOSE 80
RUN useradd --system --no-create-home app
USER app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","80"]
