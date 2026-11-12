/**
 * Pantalla de gestión de proyectos (issue #7), solo para el administrador: listado y alta.
 *
 * Para qué: listado de todos los proyectos con su tipo y su número de documentos, formulario para
 * crear uno nuevo y botón para borrarlo. Pulsar el nombre lleva al detalle (ProyectoDetalle.tsx),
 * donde se añaden y borran sus documentos.
 *
 * Quién lo usa: App.tsx, en la ruta /proyectos, solo si el usuario es administrador. Usa las
 * funciones de proyectos de src/api/client.ts y el aviso de components/ConfirmDialog.tsx.
 *
 * Notas:
 *  - Nombre, tipo y descripción se editan en el detalle (ProyectoDetalle.tsx), junto a sus documentos.
 *  - Borrar avisa de cuántos documentos se borrarán con él, porque no se puede deshacer.
 *  - Los errores son los de la API, tal cual («Ya existe un proyecto con ese nombre»…), y tras
 *    cada cambio se vuelve a pedir el listado (como en Roles.tsx).
 */

import { useEffect, useState, type SubmitEvent } from 'react'
import { Link } from 'react-router-dom'
import { createProject, deleteProject, listProjects, type Proyecto } from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

const VACIO = { nombre: '', tipo: '', descripcion: '' }

/** Texto del aviso de borrado según cuántos documentos tiene el proyecto. */
function avisoBorrado(p: Proyecto) {
  const docs = p.num_documentos === 0 ? 'No tiene documentos.'
    : p.num_documentos === 1 ? 'Se borrará también su documento.'
      : `Se borrarán también sus ${p.num_documentos} documentos.`
  return `${docs} No se puede deshacer.`
}

/** Gestión de proyectos: alta, listado y borrado. */
export default function Proyectos() {
  const [proyectos, setProyectos] = useState<Proyecto[] | null>(null)
  const [error, setError] = useState('')
  const [nuevo, setNuevo] = useState(VACIO)
  const [borrando, setBorrando] = useState<Proyecto | null>(null)
  const [busy, setBusy] = useState(false)

  const cargar = () => listProjects().then(setProyectos).catch((err) => setError(mensaje(err)))

  useEffect(() => {
    listProjects().then(setProyectos).catch((err) => setError(mensaje(err)))
  }, [])

  /** Ejecuta una acción sobre la API; si va bien recarga el listado, si falla muestra el error. */
  async function accion(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true)
    setError('')
    try {
      await fn()
      await cargar()
      return true
    } catch (err) {
      setError(mensaje(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function crear(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    if (await accion(() => createProject(nuevo))) setNuevo(VACIO)
  }

  async function confirmarBorrado() {
    if (!borrando) return
    const p = borrando
    setBorrando(null)
    await accion(() => deleteProject(p.id))
  }

  return (
    <main className="pagina">
      <h1>Proyectos</h1>

      <form className="fila" onSubmit={crear} aria-label="Nuevo proyecto">
        <label>
          Nombre
          <input value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} maxLength={100} />
        </label>
        <label>
          Tipo
          <input value={nuevo.tipo} onChange={(e) => setNuevo({ ...nuevo, tipo: e.target.value })} maxLength={100} />
        </label>
        <label className="ancho">
          Descripción
          <input value={nuevo.descripcion} onChange={(e) => setNuevo({ ...nuevo, descripcion: e.target.value })} maxLength={1000} />
        </label>
        <button type="submit" disabled={busy || !nuevo.nombre.trim()}>Crear proyecto</button>
      </form>

      {error && <p role="alert" className="error">{error}</p>}

      {proyectos === null ? (
        !error && <p className="hint">Cargando…</p>
      ) : proyectos.length === 0 ? (
        <p className="hint">Todavía no hay proyectos. Crea el primero con el formulario de arriba.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Nombre</th><th>Tipo</th><th>Documentos</th><th><span className="oculto">Acciones</span></th></tr>
          </thead>
          <tbody>
            {proyectos.map((p) => (
              <tr key={p.id}>
                <td><Link to={`/proyectos/${p.id}`}>{p.nombre}</Link></td>
                <td>{p.tipo ?? '—'}</td>
                <td>{p.num_documentos}</td>
                <td className="acciones">
                  <button className="peligro" disabled={busy} onClick={() => setBorrando(p)}>Borrar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ConfirmDialog
        open={borrando !== null}
        titulo={`¿Borrar el proyecto «${borrando?.nombre ?? ''}»?`}
        mensaje={borrando ? avisoBorrado(borrando) : ''}
        confirmar="Borrar"
        onConfirm={confirmarBorrado}
        onCancel={() => setBorrando(null)}
      />
    </main>
  )
}
