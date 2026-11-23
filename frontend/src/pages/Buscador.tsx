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
 */

import { useEffect, useState, type SubmitEvent } from 'react'
import { Link } from 'react-router-dom'
import { listProjects, searchFragments, type Proyecto, type ResultadoBusqueda } from '../api/client'

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

/** Puntuación con 3 decimales y coma decimal; «—» si no hay. */
const num = (x: number | null) =>
  x === null ? '—' : x.toLocaleString('es-ES', { minimumFractionDigits: 3, maximumFractionDigits: 3 })

export default function Buscador() {
  const [proyectos, setProyectos] = useState<Proyecto[]>([])
  const [pregunta, setPregunta] = useState('')
  const [proyectoId, setProyectoId] = useState('')
  const [resultados, setResultados] = useState<ResultadoBusqueda[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listProjects().then(setProyectos).catch((err) => setError(mensaje(err)))
  }, [])

  async function buscar(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setResultados(null)
    try {
      setResultados(await searchFragments(pregunta.trim(), proyectoId ? Number(proyectoId) : null))
    } catch (err) {
      setError(mensaje(err))
    } finally {
      setBusy(false)
    }
  }

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

      {resultados !== null && (resultados.length === 0 ? (
        <p className="hint">No hay trozos que se parezcan</p>
      ) : (
        <section className="resultados" aria-label="Resultados">
          {resultados.map((r, i) => (
            <article key={`${r.documento_id}-${i}`} className="resultado">
              <header>
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
      ))}
    </main>
  )
}
