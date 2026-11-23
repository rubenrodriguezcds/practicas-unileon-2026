# Asistente IA, fase 1: leer e indexar los documentos — diseño (BORRADOR)

> **Borrador para revisar en equipo.** Sale de la propuesta de IA (v2) y de la prueba de Docling
> (`prueba_docling/INFORME.md`, rama `prueba/extraccion-docling`). La fase 2 (el chat que
> pregunta y responde citando) va en otra spec.

## Qué se quiere

Que cada documento subido a un proyecto se lea, se trocee y se guarde de forma que luego se pueda
buscar por significado y por palabras (búsqueda híbrida), sin que quien sube tenga que esperar ni
hacer nada.

## Alcance

- **Dentro**: conversión con Docling (y LibreOffice / `vsdx` donde haga falta), troceado,
  embeddings, guardado en Postgres, estado de indexado visible en la ficha del proyecto, borrado en
  cascada, reintentos.
- **Fuera**: el chat y sus guardrails (fase 2), permisos por usuario sobre proyectos (no existen
  aún), reindexar al cambiar de modelo (se hará con un script cuando haga falta), descripción de
  imágenes con IA.

## Cómo funciona

```
subir documento (endpoint actual, sin cambios)
      │
      ▼
documentos ──► indexador (contenedor nuevo, en segundo plano)
                 1. coge un documento pendiente (cola en Postgres, SKIP LOCKED)
                 2. si hace falta, LibreOffice lo convierte a PDF
                 3. Docling: JSON del documento + trozos (texto, sección, páginas)
                 4. Visio .vsdx: además, texto de las formas y conexiones con `vsdx`
                 5. embeddings de los trozos (API de OpenAI)
                 6. guarda JSON y trozos; estado «hecho» (o «error» con el motivo)
```

**El estado se deriva**: un documento sin fila en `indexado` está pendiente. Así el endpoint de
subida no cambia y es imposible que un documento se quede sin apuntar a la cola.

### Qué se hace con cada tipo (comprobado en la prueba)

| Tipo | Camino | Cita por |
|---|---|---|
| PDF con texto | Docling (copia el texto, el modelo detecta títulos y tablas) | página |
| PDF escaneado, imagen | Docling con OCR en español | página |
| `.docx`, `.pptx`, `.xlsx` | Docling directo | sección / diapositiva / hoja |
| `.doc`, `.ppt` | **LibreOffice → PDF** → Docling (directos fallan) | página |
| `.vsdx` | **LibreOffice → PDF** → Docling + `vsdx` (texto y conexiones «A → B») | página |
| `.vsd` | **LibreOffice → PDF** → Docling (sin conexiones) | página |
| `.txt`, `.csv`, `.md`, `.gif`, `.webp` | Docling directo | - |
| `.odt`, `.odp` | **LibreOffice → PDF** → Docling | página |
| `.xls`, `.ods` | **LibreOffice → `.xlsx`** → Docling (en PDF la hoja pierde la tabla) | hoja |

## Piezas

| Pieza | Qué es | Cambio |
|---|---|---|
| `db` | Postgres | Imagen base `postgres:16` → `pgvector/pgvector:pg16` (misma Postgres 16 con la extensión) |
| `docling` | `docling-serve-cpu` versión fijada | Servicio nuevo, **sin puertos publicados** (en `main` no se abre la interfaz web) |
| `indexador` | Python 3.12 + LibreOffice sin interfaz + `vsdx` + `httpx` | Servicio y carpeta nuevos (`indexador/`); habla con `db` y `docling` por la red interna |
| API | FastAPI actual | Solo lectura: el listado de documentos devuelve también el estado de indexado |
| Frontend | Ficha del proyecto | Columna «Asistente»: pendiente · indexando · listo · error (con el motivo) |

Dentro del indexador, un fichero por responsabilidad: `cola.py` (coger y marcar trabajos),
`convertir.py` (LibreOffice), `docling_cliente.py`, `visio.py`, `embeddings.py`, `guardar.py`,
`main.py` (el bucle). `embeddings.py` expone una sola función `vectorizar(textos) -> vectores`:
cambiar de proveedor (p. ej. un modelo local en el servidor de la empresa) es cambiar ese fichero.

## Esquema (migración `005_indexado.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Una fila por documento que el indexador ha cogido. Sin fila = pendiente.
CREATE TABLE IF NOT EXISTS indexado (
  documento_id    INTEGER PRIMARY KEY REFERENCES documentos (id) ON DELETE CASCADE,
  estado          VARCHAR(20) NOT NULL,   -- procesando | hecho | error
  intentos        INTEGER     NOT NULL DEFAULT 0,
  error           TEXT,
  docling_json    JSONB,                  -- para volver a trocear sin reprocesar el original
  docling_version VARCHAR(20),
  actualizado     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fragmentos (
  id           SERIAL  PRIMARY KEY,
  documento_id INTEGER NOT NULL REFERENCES documentos (id) ON DELETE CASCADE,
  proyecto_id  INTEGER NOT NULL REFERENCES proyectos (id) ON DELETE CASCADE, -- filtrar por proyecto
  orden        INTEGER NOT NULL,
  texto        TEXT    NOT NULL,
  titulos      TEXT[],                    -- secciones de las que cuelga
  paginas      INTEGER[],                 -- vacío en Word (no tiene páginas fijas)
  embedding    halfvec(1024),
  busqueda     tsvector                   -- español sin acentos (lo rellena el indexador)
);
-- + índice HNSW (coseno) sobre embedding, GIN sobre busqueda, índice por proyecto_id
```

- `halfvec(1024)`: OpenAI permite pedir 1024 dimensiones, y es el mismo tamaño que los modelos
  locales candidatos (bge-m3): cambiar de modelo no cambia la tabla (sí exige revectorizar).
  `halfvec` ocupa la mitad que `vector` con pérdida despreciable.
- Borrar un documento o un proyecto borra sus trozos sola la bbdd.
- **Tablas nuevas en la misma bbdd**, no una bbdd aparte: así las claves foráneas a `documentos` y
  `proyectos` (borrado en cascada) funcionan, la búsqueda puede cruzar trozos con proyectos (y
  más adelante con permisos) en una sola consulta, y hay una única copia de seguridad.

### Cuando escale

pgvector (coste 0, misma Postgres) aguanta hasta unos 5-10 millones de trozos. Si se supera eso, o
la búsqueda pasa de ~200 ms con filtros, se migra a una base vectorial dedicada: **Qdrant**
(libre, autoalojable en el servidor de la empresa) o **Pinecone** (gestionada, de pago, desde
~50 $/mes y con los datos fuera). Para que la migración no toque el resto, el acceso a los
vectores va en un único módulo (`guardar.py` al escribir; el buscador de la fase 2 al leer).

## Cola y errores

- El indexador busca documentos sin fila en `indexado` (o en `error` con `intentos < 3`) con
  `FOR UPDATE SKIP LOCKED`: se pueden lanzar varios indexadores sin pisarse.
- Un «error» se reintenta esperando tantos minutos como intentos lleve (Docling u OpenAI caídos
  no gastan los tres intentos en segundos).
- Un `procesando` de hace más de 30 min se considera colgado y se reintenta.
- **Por qué Postgres y no RabbitMQ o Kafka** (decidido el 23-11): los tres son gratis, pero un
  broker añade un contenedor y obliga a tocar la subida, y entre «guardar el documento» y «publicar
  el mensaje» el aviso se puede perder. Con el estado derivado eso no puede pasar. RabbitMQ sería el
  paso siguiente si hubiera que repartir el trabajo entre muchas máquinas (solo cambia `cola.py`).
- Nada falla en silencio: cada error queda en el log del indexador y en `indexado.error`, y la
  ficha del proyecto lo muestra. Tres fallos seguidos lo dejan en «error» hasta que alguien lo mire.
- Si Docling o OpenAI no responden, el documento sigue pendiente y se reintenta; la app no se entera.

## Embeddings

- Modelo: **OpenAI `text-embedding-3-small`**, 1024 dimensiones, 0,02 $ por millón de tokens
  (precio oficial, revisado el 13-11-2026).
- Variable nueva en `.env`: `OPENAI_API_KEY` (también en `.env.example` y en el README). Sin ella el
  indexador arranca, avisa en el log y deja los documentos en «error: falta OPENAI_API_KEY».
- **Provisional**: las APIs externas (OpenAI aquí, Claude en la fase 2) solo se usan mientras no
  haya servidor y con **datos de prueba**, porque el texto de los trozos sale hacia el proveedor.
  Con el servidor de la empresa se pasa a modelos locales (embeddings con bge-m3 u otro de 1024
  dimensiones): se cambia `embeddings.py` y se revectoriza, sin tocar la tabla.

## Pruebas

- Indexador con TDD y sin servicios reales: dobles de Docling, OpenAI y la bbdd, como en la API.
- Casos: cada tipo de la tabla, documento que falla 3 veces, documento borrado mientras se
  indexa, `procesando` colgado, falta de API key, Docling caído.
- A mano: subir las muestras de `prueba_docling/muestras/` y ver los estados y los trozos en la bbdd.

## Ver y comprobar lo indexado (por concretar)

- **Ver las tablas** con un cliente de Postgres (DBeaver, pgAdmin) por el puerto 1521: estados,
  trozos, secciones y páginas. El vector en sí es una lista de 1024 números: no se lee a ojo.
- **Buscador de prueba**: escribir una pregunta y ver los trozos más parecidos con su puntuación
  (por significado, por palabras y combinados). Es la forma real de comprobar que el indexado
  sirve, y la base del buscador de la fase 2. Será una **página «Buscador»** de la app, solo para
el administrador (decidido el 16-11).

## Decidido (23-11)

4. Cola en Postgres, no RabbitMQ ni Kafka (ver «Cola y errores»).
5. Docling se llama una sola vez por documento: trozos + JSON (comprobado contra docling-serve 1.38.2).

## Decidido (16-11)

1. APIs externas solo provisionales y con datos de prueba; con el servidor, modelos locales.
2. No se guarda el Markdown: se saca del JSON si hace falta.
3. El estado de indexado lo ve todo el que vea el proyecto (hoy solo el administrador).
