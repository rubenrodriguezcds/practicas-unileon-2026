# Informe: prueba de extracción con Docling (13-11-2026)

Docling `docling-serve-cpu` v1.38.2 en CPU, con OCR en español y tablas en modo preciso. Se
usaron 11 muestras **ficticias** generadas por `generar_muestras.py`, con frases conocidas para
comprobar de forma automática que el texto sale entero.

## Resultado por documento

| Muestra | Frases | Tiempo | Tablas | Página o diapositiva | Observaciones |
|---|---|---|---|---|---|
| `informe_con_bordes.pdf` | 5/5 | 6-8 s (2 pág.) | correcta | sí | El título del documento sale después de la tabla |
| `informe.pdf` (tabla sin bordes) | 5/5 | 4 s (2 pág.) | **texto plano** | sí | Sin líneas, la tabla no se detecta; título descolocado |
| `acta_escaneada.pdf` / `.png` | 4/4 | 8 s | - | sí | OCR correcto, acentos incluidos; sale en un solo párrafo |
| `memoria.docx` | 5/5 | 2 s | correcta | **no** | Word no tiene páginas fijas: se cita por sección |
| `presentacion.pptx` | 6/6 | 2 s | correcta | sí | Cajas de un diagrama: texto sí, relaciones no |
| `presupuesto.xlsx` | 3/3 | 2 s | correcta | hoja | - |
| `memoria.doc` | 0/5 → 5/5 | 4 s | - | sí | **Falla directo**; bien convertido antes a PDF con LibreOffice |
| `presentacion.ppt` | 0/6 → 6/6 | 8 s | - | sí | Igual que `.doc` |
| `arquitectura.vsdx` → PDF | 3/3 | 2 s | - | sí | Texto sí, **conexiones no** |
| `arquitectura.vsdx` con `visio.py` | 3/3 | <1 s | - | página | Texto **y conexiones** «A → B» |

Memoria máxima del contenedor de Docling: **2,5 GB**. El modo de tablas rápido dio el mismo
resultado que el preciso con estas muestras (con tablas reales más complejas puede no ser así).

## Rúbrica (0-2)

| Muestra | Texto | Orden | Tablas | Títulos | Página | Acentos | Media |
|---|---|---|---|---|---|---|---|
| PDF con bordes | 2 | 1 | 2 | 1 | 2 | 2 | 1,7 |
| PDF sin bordes | 2 | 1 | 1 | 1 | 2 | 2 | 1,5 |
| DOCX | 2 | 2 | 2 | 2 | 1 (sección) | 2 | 1,8 |
| PPTX | 2 | 2 | 2 | 2 | 2 | 2 | 2,0 |

Se cumplen los criterios de éxito: media ≥ 1,5 en PDF, DOCX y PPTX, OCR legible en español,
menos de 10 s por página y Visio con texto y conexiones (con `visio.py`).

## En qué formato sale y qué hace falta después

- Docling devuelve **Markdown** (texto con títulos `#` y tablas `| |`) y **JSON** (la estructura
  completa, con la página de cada elemento).
- Además trocea (`/v1/chunk/hybrid/file`): cada trozo trae su `text`, los `headings` de los que
  cuelga y los `page_numbers`. Las tablas se pasan a frases («Migración, Duración = 6 semanas»),
  que es lo mejor para buscar por significado. **No hace falta convertir nada más**: el trozo va
  tal cual a los embeddings y sus títulos y página sirven para citar.
- Excepciones: `.doc`, `.ppt` y Visio pasan antes por LibreOffice (a PDF), y los `.vsdx` además
  por `visio.py` para no perder las conexiones.

## Decisión propuesta

1. **Docling sí**, como servicio aparte (`docling-serve-cpu`, versión fijada), sin publicar puertos.
2. Opciones: OCR activado con `ocr_lang=es` y `table_mode=accurate`.
3. Troceado con el de Docling (`hybrid`); citar por página en PDF y PowerPoint, y por sección en Word.
4. `.doc` y `.ppt`: LibreOffice a PDF antes de Docling (contenedor con LibreOffice sin interfaz).
5. Visio: `.vsdx` con `vsdx` (texto + conexiones) más la versión PDF; `.vsd` con LibreOffice a PDF.

## Lo que no se ha podido comprobar

- **Documentos reales**: las muestras son sencillas y ficticias. Faltan maquetas complejas (varias
  columnas, cabeceras, texto dentro de imágenes de PowerPoint) y PDF escaneados de baja calidad.
- **Visio real**: el `.vsdx` de prueba está escrito a mano y es mínimo; uno hecho con Visio usa
  maestros y plantillas. Tampoco hay ningún `.vsd`, porque no se pueden generar sin Visio.
- **Documentos grandes**: no se han medido tiempos ni memoria con documentos de cientos de páginas.
- Los tiempos tienen un mínimo de unos 2 s por documento que parece de la propia espera del
  servidor, no del tamaño del documento.
