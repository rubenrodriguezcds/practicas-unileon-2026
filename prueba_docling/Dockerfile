# Imagen de los scripts de la prueba: Python + LibreOffice sin interfaz.
# LibreOffice genera las muestras .doc/.ppt y convierte a PDF lo que Docling no lee (Visio).
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libreoffice-writer-nogui libreoffice-impress-nogui libreoffice-calc-nogui \
      libreoffice-draw-nogui fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
