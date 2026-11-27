/**
 * Buscador de prueba del asistente (fase 1), solo para el administrador.
 *
 * Para qué: escribir una pregunta y ver los trozos de documentos que más se le parecen, para
 * comprobar que el indexado sirve antes de montar el chat (fase 2). Cada resultado enseña su
 * documento (enlace a la ficha del proyecto), sección, páginas, el texto del trozo y tres
 * puntuaciones: por significado (coseno del vector), por palabras (ts_rank) y la combinada (RRF),
 * que es la que ordena.
 *
 * Quién lo usa: App.tsx, en la ruta /buscador, solo si el usuario es administrador.
 *
 * Notas:
 *  - La búsqueda necesita Ollama (embeddings): si no responde, la API da 503 y se muestra su mensaje.
 *  - «—» en una puntuación = ese trozo no salió en ese ranking (p. ej. ninguna palabra coincide).
 *  - Resumen con IA: cuando llegan los resultados se pide aparte (tarda segundos) y se pinta encima.
 *    Sus citas [n] son botones que llevan al resultado n y lo resaltan. Solo se pide si hay
 *    resultados; si falla, se ve el motivo en su bloque y los resultados siguen ahí.
 *  - Si el resumen dice que no lo encuentra, los resultados se pliegan como «poco relevantes»: el
 *    buscador siempre devuelve los más parecidos aunque ninguno lo sea, y el modelo, que los lee,
 *    es quien mejor lo sabe (la puntuación de parecido sola no basta con trozos cortos).
 *  - Si se lanza otra búsqueda antes de que acabe la anterior, la respuesta vieja se descarta.
 */

import { useEffect, useRef, useState, type ReactNode, type SubmitEvent } from 'react'
import { Link } from 'react-router-dom'
import { listProjects, searchFragments, summarizeSearch, type Proyecto, type ResultadoBusqueda } from '../api/client'

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

/** Puntuación con 3 decimales y coma decimal; «—» si no hay. */
const num = (x: number | null) =>
  x === null ? '—' : x.toLocaleString('es-ES', { minimumFractionDigits: 3, maximumFractionDigits: 3 })

type Resumen =
  | { estado: 'cargando' }
  | { estado: 'listo'; texto: string; fuentes: number; encontrado: boolean }
  | { estado: 'error'; mensaje: string }

/** Texto del resumen con cada cita [1] o [1, 2] convertida en botones que llevan a su resultado. */
function conCitas(texto: string, fuentes: number, ir: (n: number) => void): ReactNode[] {
  return texto.split(/(\[\d+(?:\s*,\s*\d+)*\])/).map((parte, i) => {
    const numeros = parte.match(/^\[([\d,\s]+)\]$/)?.[1].split(',').map(Number).filter((n) => n >= 1 && n <= fuentes)
    if (!numeros?.length) return parte
    return (
      <span key={i} className="citas">
        {numeros.map((n) => (
          <button key={n} type="button" className="cita" aria-label={`Ir a la fuente ${n}`} onClick={() => ir(n)}>{n}</button>
        ))}
      </span>
    )
  })
}

export default function Buscador() {
  const [proyectos, setProyectos] = useState<Proyecto[]>([])
  const [pregunta, setPregunta] = useState('')
  const [proyectoId, setProyectoId] = useState('')
  const [resultados, setResultados] = useState<ResultadoBusqueda[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resumen, setResumen] = useState<Resumen | null>(null)
  const [resaltado, setResaltado] = useState<number | null>(null)
  const ultima = useRef(0) // número de la última búsqueda: las respuestas de otras se descartan

  useEffect(() => {
    listProjects().then(setProyectos).catch((err) => setError(mensaje(err)))
  }, [])

  async function buscar(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setResultados(null)
    setResumen(null)
    setResaltado(null)
    const esta = ++ultima.current
    const q = pregunta.trim()
    const pid = proyectoId ? Number(proyectoId) : null
    let encontrados: ResultadoBusqueda[]
    try {
      encontrados = await searchFragments(q, pid)
    } catch (err) {
      if (esta === ultima.current) setError(mensaje(err))
      return
    } finally {
      if (esta === ultima.current) setBusy(false)
    }
    if (esta !== ultima.current) return
    setResultados(encontrados)
    if (encontrados.length === 0) return
    setResumen({ estado: 'cargando' })
    try {
      const r = await summarizeSearch(q, pid)
      if (esta !== ultima.current) return
      setResumen(r.resumen ? { estado: 'listo', texto: r.resumen, fuentes: r.fuentes, encontrado: r.encontrado } : null)
    } catch (err) {
      if (esta === ultima.current) setResumen({ estado: 'error', mensaje: mensaje(err) })
    }
  }

  function irAFuente(n: number) {
    setResaltado(n)
    document.getElementById(`resultado-${n}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const pocoRelevantes = resumen?.estado === 'listo' && !resumen.encontrado
  const lista = resultados?.length ? (
    <section className="resultados" aria-label="Resultados">
      {resultados.map((r, i) => (
        <article
          key={`${r.documento_id}-${i}`}
          id={`resultado-${i + 1}`}
          className={resaltado === i + 1 ? 'resultado resaltado' : 'resultado'}
        >
          <header>
            <span className="numero">[{i + 1}]</span>
            <Link to={`/proyectos/${r.proyecto_id}`}>{r.documento}</Link>
            <span className="seccion">{r.proyecto}</span>
            {r.titulos.length > 0 && <span className="seccion">{r.titulos.join(' › ')}</span>}
            {r.paginas.length > 0 && (
              <span className="seccion">{r.paginas.length === 1 ? 'pág.' : 'págs.'} {r.paginas.join(', ')}</span>
            )}
          </header>
          <p className="trozo">{r.texto}</p>
          <span className="puntuaciones">
            Significado {num(r.puntuacion_vector)} · Palabras {num(r.puntuacion_texto)} · Combinada {num(r.puntuacion)}
          </span>
        </article>
      ))}
    </section>
  ) : null

  return (
    <main className="pagina">
      <h1>Buscador</h1>
      <p className="hint">Prueba de la búsqueda del asistente: los trozos de documentos que más se parecen a la pregunta.</p>

      <form className="fila" onSubmit={buscar} aria-label="Buscar">
        <label className="ancho">
          Pregunta
          <input id="pregunta" value={pregunta} onChange={(e) => setPregunta(e.target.value)} maxLength={500} autoComplete="off" />
        </label>
        <label>
          Proyecto
          <select id="proyecto" value={proyectoId} onChange={(e) => setProyectoId(e.target.value)}>
            <option value="">Todos los proyectos</option>
            {proyectos.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy || !pregunta.trim()}>Buscar</button>
      </form>

      {error && <p role="alert" className="error">{error}</p>}
      {busy && <p className="hint">Buscando…</p>}

      {resumen && (
        <section className="resumen-ia" aria-label="Resumen con IA" aria-live="polite" aria-busy={resumen.estado === 'cargando'}>
          <h2>Resumen con IA</h2>
          {resumen.estado === 'cargando' && <p className="hint">Generando resumen…</p>}
          {resumen.estado === 'listo' && <p className="texto">{conCitas(resumen.texto, resumen.fuentes, irAFuente)}</p>}
          {resumen.estado === 'error' && <p className="error">{resumen.mensaje}</p>}
          <p className="aviso">Generado con IA a partir de los documentos: compruébalo en las fuentes.</p>
        </section>
      )}

      {resultados !== null && resultados.length === 0 && <p className="hint">No hay trozos que se parezcan</p>}
      {lista && (pocoRelevantes ? (
        <details className="poco-relevantes">
          <summary>Ver {resultados?.length} resultados poco relevantes</summary>
          {lista}
        </details>
      ) : lista)}
    </main>
  )
}
