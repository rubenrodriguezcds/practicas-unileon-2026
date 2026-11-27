# Validaciones de contenido por proyecto: diseño (BORRADOR)

> **Borrador para revisar en equipo.** Sale de la reunión con el tutor del 27-11. Se apoya en la
> fase 1 del asistente (indexado y buscador, rama `feature/ia-indexado`). Lo marcado como
> **A decidir** hay que cerrarlo antes de repartir el trabajo.

## Qué se quiere

Que el director de proyectos pueda comprobar de un vistazo si la documentación de un proyecto
tiene **lo mínimo** y rechazarla si está incompleta. El tutor lo comparó con un «compilador»:
una lista de comprobaciones que el proyecto tiene que pasar. El primer caso de uso son los
proyectos de red:

| Validación | Resultado |
|---|---|
| ¿Aparecen las VLAN? | ✅ en `diseño_red.pdf`, pág. 3 |
| ¿Está definida la tabla de rutas? | ❌ no aparece en ningún documento |

Es un punto de partida que habrá que afinar, pero la idea vale para más cosas que la
documentación de red.

## Alcance

- **Dentro**:
  - Validaciones asociadas a cada proyecto, de dos tipos: patrón de texto e IA.
  - Ejecutarlas sobre todos los documentos ya indexados del proyecto.
  - Guardar el resultado con su prueba (documento, página y trozo).
  - Una pestaña «Validación» en la ficha del proyecto.
- **Fuera** (de momento):
  - Validar automáticamente cada vez que se indexa un documento.
  - Permisos para que lo vean otros usuarios (hoy los proyectos son solo del administrador).
  - Validaciones sobre la estructura del documento (por ejemplo, «el apartado 3 debe tener una tabla»).

## Tipos de validación

| Tipo | Qué se escribe | Cómo se comprueba | Cuánto tarda |
|---|---|---|---|
| **Patrón** (estática) | Una expresión regular, p. ej. `\bVLAN\s*\d+` | Postgres busca el patrón (`~*`, sin distinguir mayúsculas) en el `texto` de los `fragmentos` del proyecto. Pasa si algún trozo coincide | Milisegundos |
| **IA** | Una pregunta, p. ej. «¿Está definida la tabla de rutas?» | 1) Se buscan los trozos más parecidos del proyecto con la búsqueda híbrida (`db.search_fragments`, la del buscador). 2) Se le pasan a Gemma (`gemma4:e2b` en Ollama) con la pregunta. 3) Gemma responde en JSON si se cumple y **en qué trozo lo ha visto** | ~40-60 s (medido 27-11: lee ~110 tokens/s y escribe ~4,4 tokens/s) |

Por qué los dos tipos:
- El **patrón** es exacto, rápido y no se equivoca, pero solo encuentra lo que se escribe igual.
- La **IA** entiende el significado: encuentra la tabla de rutas aunque se llame «routing table»
  o «rutas estáticas». A cambio es lenta y puede equivocarse.

### Reglas para que la IA no «apruebe» sin pruebas

- **Respuesta en JSON con esquema fijo**, usando el `format` de Ollama:
  `{"cumple": bool, "trozo": int|null, "explicacion": str}`. Se usa `think: false` para que
  responda sin pensar en voz alta y tarde menos.
- **Sin trozo citado no hay aprobado.** Si dice `cumple: true` pero no cita un trozo de los que
  se le pasaron, el resultado es ❌ con «la IA no indicó dónde lo encontró».
- **Sin trozos parecidos no se pregunta.** Si el proyecto no tiene trozos, o ninguno pasa un
  parecido mínimo, el resultado es ❌ «no aparece en ningún documento», sin gastar una llamada a
  Gemma. Es el umbral pendiente P19. **A decidir**: el valor del umbral (las pruebas dan ~0,6 si
  está y ~0,3 si no).
- La prueba guardada es **el trozo real**, no lo que diga la IA, para que el director lo compruebe.

## Esquema (migración `006_validaciones.sql`)

```sql
CREATE TABLE IF NOT EXISTS validaciones (
  id          SERIAL       PRIMARY KEY,
  proyecto_id INTEGER      NOT NULL REFERENCES proyectos (id) ON DELETE CASCADE,
  nombre      VARCHAR(200) NOT NULL,          -- lo que se ve en la pestaña
  tipo        VARCHAR(10)  NOT NULL CHECK (tipo IN ('patron', 'ia')),
  criterio    TEXT         NOT NULL,          -- la expresión regular o la pregunta
  orden       INTEGER      NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS validaciones_proyecto ON validaciones (proyecto_id);

-- Último resultado de cada validación (se sobrescribe al volver a validar).
CREATE TABLE IF NOT EXISTS validacion_resultados (
  validacion_id INTEGER     PRIMARY KEY REFERENCES validaciones (id) ON DELETE CASCADE,
  estado        VARCHAR(10) NOT NULL CHECK (estado IN ('ok', 'falla', 'error')),
  explicacion   TEXT,                         -- «no aparece…», lo que dice la IA o el motivo del error
  fragmento_id  INTEGER     REFERENCES fragmentos (id) ON DELETE SET NULL,  -- la prueba
  ejecutada     TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- Sin fila en `validacion_resultados` = **sin validar** (como `indexado`: el estado se deriva).
- `fragmento_id` con `ON DELETE SET NULL`: si se borra o reindexa el documento que era la prueba,
  el resultado se queda sin prueba y la pestaña avisa de que hay que volver a validar.
- **A decidir**: ¿guardar un historial de resultados (quién validó y cuándo)? Para «rechazar» un
  proyecto quizá haga falta. Propuesta: de momento solo el último resultado.

## API (solo administrador, como el resto de proyectos)

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/proyectos/{id}/validaciones` | Lista con su último resultado y la prueba (documento, páginas y texto del trozo) |
| POST | `/api/proyectos/{id}/validaciones` | Crear `{nombre, tipo, criterio}`. 422 si el patrón no es una expresión regular válida |
| PUT / DELETE | `/api/validaciones/{id}` | Editar o borrar (al editar se borra su resultado) |
| POST | `/api/validaciones/{id}/ejecutar` | Ejecuta **una** validación y devuelve el resultado. 503 si Ollama no responde |

**Una petición por validación, no una para todas**: con IA cada una tarda ~1 min, y una petición
de varios minutos se cortaría. La pestaña las lanza una tras otra y va pintando cada resultado.

## Pantalla: pestaña «Validación» en la ficha del proyecto

- Una tabla con cada validación: ✅ cumple · ❌ no cumple · ⚠️ error · «—» sin validar; su nombre,
  el tipo y la prueba (documento y página, con el trozo al desplegar).
- Un botón **«Validar todo»**, que las ejecuta en orden con un aviso de «Validando 2 de 5…», y un
  botón «Validar» por fila.
- Un formulario para añadir una validación (nombre, tipo y patrón o pregunta) y botones para
  editar y borrar.
- Un resumen arriba, p. ej. «3 de 5 cumplen», para que el director decida de un vistazo.
- **A decidir**: ¿«Documentos» y «Validación» van como pestañas, o la validación como sección
  debajo de los documentos? Lo más sencillo es la sección.

## Cómo se asignan a un proyecto

**A decidir** (el tutor lo dejó abierto). Opciones:
1. **Por proyecto, a mano**: cada proyecto tiene las suyas. Es lo más sencillo y basta para la
   demo del 11-12.
2. **Plantillas por tipo de proyecto**: una plantilla «Red» con sus validaciones, que se copian al
   crear un proyecto de ese `tipo`. Exige una tabla de plantillas y fijar los tipos (hoy `tipo`
   es texto libre, ver D31).
3. **Copiar las de otro proyecto**: un botón «Copiar validaciones de…». Es un término medio.

Propuesta: **la 1 ahora**, y la 2 o la 3 después de la presentación.

## Reparto propuesto

- **Uno:** migración 006, CRUD de validaciones en la API, validaciones de patrón y su parte de los tests.
- **Otro:** validaciones con IA (búsqueda, prompt, JSON, reglas anti-alucinación) y la pestaña.
- Juntos: preparar unas muestras de proyecto de red (documentos ficticios con y sin VLAN y tabla
  de rutas) para probarlo y para la demo.

## Pruebas

- Tests con dobles (bbdd y Ollama), como en la fase 1:
  - patrón que coincide y que no;
  - patrón no válido → 422;
  - la IA dice que sí con trozo → ✅;
  - la IA dice que sí sin trozo → ❌;
  - no hay trozos parecidos → ❌ sin llamar a Gemma;
  - Ollama caído → ⚠️.
- A mano: con las muestras de red, cada validación con su ✅ o ❌ esperado, y medir cuánto tarda
  «Validar todo».

## Calendario (hasta la presentación)

| Cuándo | Qué |
|---|---|
| hasta el 29-11 | Cerrar este diseño y repartir |
| 30-11 a 6-12 | Programarlo |
| 7-8-12 | Instalación desde cero siguiendo el README |
| 9-10-12 | Presentación |
| 11-12 | Presentar |
