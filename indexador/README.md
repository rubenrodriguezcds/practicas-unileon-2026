# Indexador

Contenedor que, en segundo plano, prepara los documentos de los proyectos para el asistente de IA:
los lee con Docling, los corta en trozos con su sección y su página, los convierte en vectores y
los guarda en Postgres (pgvector) para buscarlos por significado y por palabras.

## Cómo funciona

```
subida (API, sin cambios) ──► documentos (Postgres, el fichero en BYTEA)
                                   │  sin fila en `indexado` = pendiente
                                   ▼
indexador:  1. cola.coger              coge un pendiente (FOR UPDATE SKIP LOCKED) → «procesando»
            2. convertir.convertir     LibreOffice → PDF / .xlsx si Docling no abre el formato
            3. docling_cliente.trocear POST http://docling:5001/v1/chunk/hybrid/file → trozos + JSON
            4. visio (.vsdx)           texto de las formas y conexiones «A → B»
            5. embeddings              vectores de 1024 dimensiones
            6. guardar                 trozos en `fragmentos`, estado «hecho» (o «error» con el motivo)
```

- **La cola está en Postgres**: un documento sin fila en `indexado` está pendiente, así que la
  subida no cambia y ningún documento se queda fuera. Se pueden lanzar varios indexadores: el
  `SKIP LOCKED` evita que dos cojan el mismo.
- **Reintentos**: un fallo se reintenta (esperando 1 min, luego 2) hasta 3 veces; después queda en
  «error» con el motivo, visible en la ficha del proyecto. Un «procesando» de más de 30 min se da
  por colgado y se reintenta.
- **Docling** es la imagen oficial `docling-serve` (servicio `docling` del compose). Una sola
  llamada devuelve los trozos y el documento convertido en JSON, que se guarda para volver a
  trocear sin reprocesar el original.

## Qué camino sigue cada tipo

| Tipo | Camino |
|---|---|
| `.pdf`, `.docx`, `.pptx`, `.xlsx`, imágenes, `.txt`, `.md`, `.csv` | Docling directo (OCR en español solo donde no hay texto digital) |
| `.doc`, `.ppt`, `.odt`, `.odp`, `.vsd` | LibreOffice → PDF → Docling |
| `.xls`, `.ods` | LibreOffice → `.xlsx` → Docling (en PDF una hoja pierde la tabla) |
| `.vsdx` | LibreOffice → PDF → Docling, y además `visio.py` para las conexiones |

## Ficheros

| Fichero | Para qué |
|---|---|
| `config.py` | Lee y valida el entorno (`POSTGRES_*`, `DB_HOST`, `DOCLING_URL`, `OPENAI_API_KEY`) |
| `cola.py` | Coger el siguiente documento y apuntar «hecho» o «error» |
| `convertir.py` | Camino de cada tipo y conversión con LibreOffice |
| `docling_cliente.py` | Llamada a Docling; define `Trozo` y `Resultado` |
| `visio.py` | Texto de las formas y conexiones «A → B» de un `.vsdx`, un trozo por página |
| `Dockerfile` | Python 3.12 + LibreOffice sin interfaz, sin root |

Faltan `embeddings.py`, `guardar.py`, `procesar.py` y `main.py` (el bucle), y el servicio
`indexador` en el compose.

## Pruebas

```bash
cd indexador
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # en Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m pytest -q
```

Los tests no usan servicios reales: Docling se simula con `httpx.MockTransport` y LibreOffice
sustituyendo `subprocess.run`. Para probar contra el Docling real (`docker compose up -d docling`):

```bash
docker build -t indexador-prueba indexador
docker run --rm --network practicas-unileon-2026_default \
  -v "$PWD/prueba_docling/muestras:/m:ro" indexador-prueba python -c "
import convertir, docling_cliente as d
n, b = convertir.convertir('memoria.doc', open('/m/memoria.doc', 'rb').read(), 'pdf')
print(len(d.trocear('http://docling:5001', n, b).trozos), 'trozos')"
```
