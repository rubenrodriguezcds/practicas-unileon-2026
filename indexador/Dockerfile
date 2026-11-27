# Imagen del contenedor `indexador`: Python 3.12 + LibreOffice sin interfaz.
#
# Para qué: indexar en segundo plano los documentos de los proyectos (cola en Postgres, Docling,
# embeddings, pgvector). LibreOffice convierte antes lo que Docling no abre (.doc, .ppt,
# OpenDocument, Visio); ver convertir.py.
#
# Quién lo usa: docker-compose.yml (servicio indexador, `build: ./indexador`). No publica puertos:
# solo habla con `db` y `docling` por la red interna y con la API de embeddings.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libreoffice-writer-nogui libreoffice-impress-nogui libreoffice-calc-nogui \
      libreoffice-draw-nogui fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./

# Sin root: el indexador abre ficheros subidos por usuarios con LibreOffice.
RUN useradd --create-home indexador
USER indexador

CMD ["python", "main.py"]
