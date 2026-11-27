# Prueba de extracción con Docling

Prueba de concepto para decidir si Docling extrae bien el texto de los documentos de los proyectos
(PDF, Word, PowerPoint, Excel y Visio). Va en el `docker-compose.yml` de la raíz, junto a la
app (servicios `docling` y `prueba`). No necesita API keys. Los resultados y la conclusión
están en [INFORME.md](INFORME.md).

## Qué hay

| Fichero | Para qué |
|---|---|
| `Dockerfile`, `requirements.txt` | Imagen de `prueba`: Python 3.12 + LibreOffice sin interfaz |
| `generar_muestras.py` | Crea las muestras de `muestras/` (contenido ficticio) y las frases esperadas |
| `extraer.py` | Manda cada muestra a Docling; guarda Markdown, JSON y `resultados.csv` |
| `visio.py` | Saca de los `.vsdx` el texto de las formas y las conexiones «A → B» |
| `trocear.py` | Pide a Docling los trozos ya preparados (el formato que iría al asistente) |
| `muestras/` | Documentos de prueba, todos ficticios |
| `salidas/` | Lo que generan los scripts (ignorado por git) |

## Cómo se lanza

Requisitos: Docker con unos 6 GB de memoria y unos 8 GB de disco (la imagen de Docling ocupa
4,4 GB). Desde la raíz del repositorio:

```bash
docker compose up -d     # app + Docling; Docling tarda ~1 min en estar listo
```

- **Interfaz web de Docling**: <http://localhost:5001/ui>. Se arrastra un documento, se pulsa
  *Convert* y se ven el resultado y las salidas (Markdown, JSON, trozos). El puerto se publica
  solo en `127.0.0.1` (no se ve desde la red), como excepción de esta rama de pruebas.
- **Scripts** (el servicio `prueba` tiene perfil propio: `up` no lo arranca, se usa con `run`):

```bash
docker compose run --rm prueba python generar_muestras.py    # solo si se quieren regenerar
docker compose run --rm prueba python extraer.py             # variante base
docker compose run --rm prueba python extraer.py --variante tablas-fast --tablas fast
docker compose run --rm prueba python extraer.py --variante antiguos-convertidos --convertir-antiguos
docker compose run --rm prueba python visio.py
docker compose run --rm prueba python trocear.py muestras/presentacion.pptx
```

Para probar un documento propio basta con copiarlo en `muestras/`. Si no está en
`esperado.json`, la columna `frases` sale `0/0` y hay que revisar el Markdown a mano.

## Cómo leer `salidas/<variante>/resultados.csv`

| Columna | Significado |
|---|---|
| `estado` | `success` o `failure` según Docling |
| `segundos` | Tiempo de la conversión (desde el contenedor `prueba`) |
| `paginas`, `tablas`, `caracteres` | Lo que ha detectado Docling |
| `frases` | Frases conocidas encontradas en el Markdown / frases esperadas |
| `con_pagina` | Elementos de texto con número de página / total (lo que permite citar la página) |
