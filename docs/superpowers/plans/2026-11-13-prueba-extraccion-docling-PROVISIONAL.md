# Prueba de extracción con Docling — plan PROVISIONAL

> **PROVISIONAL.** Prueba de concepto para decidir si Docling extrae bien la información de los
> documentos de los proyectos. No es la implementación de la fase 1 del asistente: no toca la app,
> no se mergea a `main` tal cual y puede cambiar según lo que salga. Cuando haya resultados se
> escribe la spec de verdad de la fase 1 (indexado).

**Rama:** `prueba/extraccion-docling` (sale de `main`).
**Contexto:** `PROPUESTA_IA_RAG_V2.md` (fase 0) y `docs/investigacion-rag/v2_4_ingesta.md`.

## Objetivo

Responder con datos, sobre documentos reales:

1. ¿Docling saca **todo el texto**, en el **orden correcto**, de PDF, Word y PowerPoint?
2. ¿Conserva **tablas**, **títulos/secciones** y el **número de página o diapositiva** (para citar)?
3. ¿Funciona el **OCR en español** en PDF escaneados e imágenes?
4. ¿Qué pasa con los formatos **antiguos** (`.doc`, `.ppt`) y con **Visio** (`.vsdx`, `.vsd`), que
   Docling no lee?
5. ¿Cuánto **tarda** por página y cuánta **memoria** usa en CPU?

## Alcance

- Dentro: extracción de texto/estructura, Visio con la librería `vsdx`, conversión de antiguos,
  tiempos y memoria, un informe con la conclusión.
- Fuera (otras pruebas): troceado definitivo, embeddings (API de OpenAI), LLM (API de Anthropic),
  base vectorial, cambios en la app. **Esta prueba no necesita ninguna API key ni gasta dinero.**

## Cómo se aísla (modular y atómico)

- Todo en una carpeta nueva `prueba_docling/` con su **propio** `docker-compose.yml`: no se toca el
  compose de la app ni sus contenedores.
- Contenedor `docling`: imagen oficial `docling-serve-cpu` (≈ 4,4 GB, puerto interno 5001), con
  versión fijada.
- Contenedor `prueba` (Python 3.12 slim): ejecuta los scripts contra `http://docling:5001` por la
  red interna. **No se publica ningún puerto** al host (regla del proyecto).
- Los documentos de muestra y las salidas **no se suben a git** (pueden ser de HPE).

## Ficheros que se crearían

| Fichero | Para qué |
|---|---|
| `prueba_docling/docker-compose.yml` | Contenedores `docling` y `prueba`, sin puertos publicados |
| `prueba_docling/Dockerfile` | Imagen de `prueba`: Python 3.12 + `httpx` + `vsdx` (+ LibreOffice si hace falta para `.vsd`) |
| `prueba_docling/requirements.txt` | Versiones fijadas de `httpx` y `vsdx` |
| `prueba_docling/extraer.py` | Manda cada documento a Docling, guarda Markdown y JSON, y apunta tiempos y estado en `resultados.csv` |
| `prueba_docling/visio.py` | Lee `.vsdx` con `vsdx`: páginas, texto de formas y conexiones «A → B» |
| `prueba_docling/README.md` | Cómo lanzarlo y cómo leer los resultados |
| `prueba_docling/muestras/` | Documentos de prueba (**ignorado por git**) |
| `prueba_docling/salidas/` | Markdown, JSON y CSV generados (**ignorado por git**) |
| `.gitignore` | Añadir `prueba_docling/muestras/` y `prueba_docling/salidas/` |
| `prueba_docling/INFORME.md` | Resultados y conclusión (al final) |

## Qué hay que instalar

- **Nada en Windows** aparte de Docker Desktop (ya está). Python va dentro del contenedor.
- Descargas: imagen `docling-serve-cpu` (≈ 4,4 GB) + `python:3.12-slim` (≈ 50 MB) + LibreOffice
  dentro de `prueba` solo si se prueban `.vsd` (≈ 300-500 MB).
- Espacio libre recomendado: **≈ 8 GB**. Memoria para Docker: **≥ 6 GB** (Docling usa unos 4 GB).

## Pasos

1. **Preparar** la carpeta, el compose, el Dockerfile y el `.gitignore`. Levantar `docling` y
   comprobar `GET /health` y `GET /v1/capabilities` (límites y formatos).
2. **Muestras**: 10-20 documentos reales en `muestras/`, al menos uno de cada:
   PDF con texto · PDF escaneado · DOCX con tablas · PPTX con diagramas/imágenes · DOC antiguo ·
   PPT antiguo · XLSX · VSDX · VSD. Además genero 3-4 sintéticos con contenido conocido (para
   comprobar automáticamente que el texto sale entero).
3. **Extracción** (`extraer.py`): `POST /v1/convert/file` con `to_formats=md` y `json`,
   `ocr_lang=es`, `table_mode=accurate`. Por documento: estado, páginas, segundos, segundos/página,
   nº de tablas, nº de caracteres, errores → `resultados.csv`; Markdown y JSON a `salidas/`.
4. **Variantes**: `table_mode=fast` vs `accurate` y OCR sí/no en los PDF, para ver qué compensa.
   Memoria con `docker stats` durante la extracción.
5. **Antiguos**: comprobar si Docling lee `.doc`/`.ppt` por sí solo; si no, convertir con
   LibreOffice y repetir.
6. **Visio** (`visio.py`): `.vsdx` con `vsdx`; `.vsd` convertido a `.vsdx` con LibreOffice.
   Comprobar que salen las páginas, el texto de las formas y las conexiones.
7. **Evaluar** cada documento con la misma rúbrica (abajo), mirando el Markdown junto al original.
8. **Informe** `INFORME.md`: tabla por documento, tiempos, memoria, problemas, y la decisión:
   Docling sí/no, opciones recomendadas y qué hace falta para Visio y antiguos. Con eso se escribe
   la spec de la fase 1.

## Rúbrica por documento (0-2 cada punto)

| Punto | 0 | 1 | 2 |
|---|---|---|---|
| Texto completo | falta mucho | falta algo | todo |
| Orden de lectura | desordenado | algún salto | correcto |
| Tablas | perdidas | texto sin estructura | tabla correcta |
| Títulos / secciones | perdidos | parciales | correctos |
| Página / diapositiva | no se sabe | aproximada | exacta |
| Acentos y caracteres | rotos | algunos | bien |

## Criterios de éxito

- Media ≥ 1,5 en la rúbrica en PDF con texto, DOCX y PPTX.
- OCR legible en español en los escaneados.
- Tiempo razonable en CPU (orientativo: < 10 s por página de media sin OCR).
- Visio: páginas y texto de las formas extraídos; las conexiones, si es posible.

## Pendiente de decidir

- Nombre de la rama (propuesto: `prueba/extraccion-docling`).
- De dónde salen las muestras y si pueden ser documentos reales de HPE (se quedan en local).
- Si se quiere ver la interfaz web de Docling (`/ui`): exigiría publicar el puerto 5001 solo en
  `127.0.0.1` durante la prueba, una excepción a la regla de puertos.
- Si los ficheros de la prueba (sin muestras ni salidas) se suben a la rama para que el compañero
  pueda repetirla.
