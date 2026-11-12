/**
 * Detalle de un proyecto (issue #7), solo para el administrador: sus datos y sus documentos.
 *
 * Para qué: ver y editar el nombre, tipo y descripción del proyecto; la tabla de sus documentos con «Ver»
 * (solo los que el navegador sabe mostrar), «Descargar» y «Borrar»; y subir documentos nuevos
 * arrastrándolos (varios a la vez) a la zona de components/DropZone.tsx.
 *
 * Quién lo usa: App.tsx, en la ruta /proyectos/:id, solo si el usuario es administrador. Se llega
 * desde el listado de Proyectos.tsx.
 *
 * Notas:
 *  - Cada archivo se sube en su propia petición y en serie (no todos a la vez, para no mandar
 *    50 MB × N de golpe). Cada uno muestra su estado: subiendo, subido o el mensaje de la API
 *    («Tipo de archivo no permitido», «Ya existe…»). Si uno falla, los demás siguen.
 *  - Los de más de MAX_MB se avisan sin subirlos. La API lo comprueba igual; esto solo evita
 *    mandar un archivo grande para nada.
 *  - Qué documentos se pueden «Ver» lo dice la API (`visible`), para no repetir la lista de tipos.
 *  - «Ver» y «Descargar» son enlaces normales: el navegador manda la cookie de sesión. «Descargar»
 *    no lleva `download`: la API ya manda `attachment`, y así, si la sesión ha caducado, la API
 *    redirige al login y el navegador lo abre (con `download` bajaría el error como si fuera el archivo).
 *  - Mientras sube, cerrar o recargar la pestaña pide confirmación: cortaría las subidas pendientes.
 *    Navegar dentro de la app no las corta (las peticiones siguen aunque se cambie de pantalla).
 */

import { useCallback, useEffect, useState, type SubmitEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  deleteDocument, documentUrl, getProject, updateProject, uploadDocument, type Documento, type ProyectoDetalle,
} from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'
import DropZone from '../components/DropZone'

/** Tamaño máximo de un documento; debe coincidir con DOCUMENTO_MAX_MB de la API (por defecto 50). */
const MAX_MB = 50

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

/** Tamaño legible: 500 B, 2 KB, 3,4 MB. */
function tamanoLegible(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1).replace('.', ',')} MB`
}

type Subida = { nombre: string; estado: 'subiendo' | 'subido' | 'error'; mensaje?: string }

const TEXTO_ESTADO = { subiendo: 'Subiendo…', subido: 'Subido' }

/** Detalle de un proyecto con sus documentos y la zona de subida. */
export default function ProyectoDetallePage() {
  const id = Number(useParams().id)
  const [proyecto, setProyecto] = useState<ProyectoDetalle | null>(null)
  const [error, setError] = useState('')
  const [subidas, setSubidas] = useState<Subida[]>([])
  const [subiendo, setSubiendo] = useState(false)
  const [borrando, setBorrando] = useState<Documento | null>(null)
  const [editando, setEditando] = useState<{ nombre: string; tipo: string; descripcion: string } | null>(null)
  const [guardando, setGuardando] = useState(false)

  // /proyectos/abc no es un proyecto: ni se pregunta a la API.
  const idValido = Number.isInteger(id) && id > 0

  const cargar = useCallback(
    () => getProject(id).then(setProyecto).catch((err) => setError(mensaje(err))),
    [id],
  )

  useEffect(() => {
    if (idValido) cargar()
  }, [cargar, idValido])

  // Con subidas pendientes, el navegador pregunta antes de cerrar o recargar la pestaña.
  useEffect(() => {
    if (!subiendo) return
    const avisar = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', avisar)
    return () => window.removeEventListener('beforeunload', avisar)
  }, [subiendo])

  async function guardar(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!editando) return
    setGuardando(true)
    setError('')
    try {
      await updateProject(id, editando)
      setEditando(null)
      await cargar()
    } catch (err) {
      setError(mensaje(err))
    } finally {
      setGuardando(false)
    }
  }

  /** Cambia el estado de la subida número `i` de la lista. */
  const marcar = (i: number, s: Partial<Subida>) =>
    setSubidas((prev) => prev.map((x, j) => (j === i ? { ...x, ...s } : x)))

  async function subir(files: File[]) {
    setError('')
    setSubiendo(true)
    setSubidas(files.map((f) => (f.size > MAX_MB * 1024 * 1024
      ? { nombre: f.name, estado: 'error', mensaje: `El archivo pasa de ${MAX_MB} MB` }
      : { nombre: f.name, estado: 'subiendo' })))
    for (const [i, f] of files.entries()) {
      if (f.size > MAX_MB * 1024 * 1024) continue
      try {
        await uploadDocument(id, f)
        marcar(i, { estado: 'subido' })
      } catch (err) {
        marcar(i, { estado: 'error', mensaje: mensaje(err) })
      }
    }
    setSubiendo(false)
    await cargar()
  }

  async function confirmarBorrado() {
    if (!borrando) return
    const doc = borrando
    setBorrando(null)
    setError('')
    try {
      await deleteDocument(doc.id)
    } catch (err) {
      setError(mensaje(err))
    }
    await cargar()
  }

  return (
    <main className="pagina">
      <p><Link to="/proyectos">← Volver a proyectos</Link></p>

      {!idValido && <p role="alert" className="error">El proyecto no existe</p>}
      {error && <p role="alert" className="error">{error}</p>}

      {proyecto && (
        <>
          <h1>{proyecto.nombre}</h1>
          {editando ? (
            <form className="fila" onSubmit={guardar} aria-label="Editar proyecto">
              <label>
                Nombre
                <input value={editando.nombre} onChange={(e) => setEditando({ ...editando, nombre: e.target.value })} maxLength={100} autoFocus />
              </label>
              <label>
                Tipo
                <input value={editando.tipo} onChange={(e) => setEditando({ ...editando, tipo: e.target.value })} maxLength={100} />
              </label>
              <label className="ancho">
                Descripción
                <input value={editando.descripcion} onChange={(e) => setEditando({ ...editando, descripcion: e.target.value })} maxLength={1000} />
              </label>
              <button type="submit" disabled={guardando || !editando.nombre.trim()}>Guardar</button>
              <button type="button" className="secundario" onClick={() => { setEditando(null); setError('') }}>Cancelar</button>
            </form>
          ) : (
            <>
              <dl className="datos">
                <dt>Tipo</dt><dd>{proyecto.tipo ?? '—'}</dd>
                <dt>Descripción</dt><dd>{proyecto.descripcion ?? '—'}</dd>
              </dl>
              <button
                type="button"
                className="secundario suelto"
                onClick={() => setEditando({ nombre: proyecto.nombre, tipo: proyecto.tipo ?? '', descripcion: proyecto.descripcion ?? '' })}
              >
                Editar
              </button>
            </>
          )}

          <h2>Documentos</h2>
          <DropZone onFiles={subir} disabled={subiendo} />

          {subidas.length > 0 && (
            <ul className="subidas" aria-label="Subidas">
              {subidas.map((s, i) => (
                <li key={i} className={s.estado}>
                  <span>{s.nombre}</span>{' '}
                  <span role={s.estado === 'error' ? 'alert' : undefined}>
                    {s.estado === 'error' ? s.mensaje : TEXTO_ESTADO[s.estado]}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {proyecto.documentos.length === 0 ? (
            <p className="hint">Este proyecto todavía no tiene documentos.</p>
          ) : (
            <table>
              <thead>
                <tr><th>Nombre</th><th>Tamaño</th><th><span className="oculto">Acciones</span></th></tr>
              </thead>
              <tbody>
                {proyecto.documentos.map((d) => (
                  <tr key={d.id}>
                    <td>{d.nombre}</td>
                    <td>{tamanoLegible(d.tamano)}</td>
                    <td className="acciones">
                      {d.visible && <a href={documentUrl(d.id, true)} target="_blank" rel="noopener noreferrer">Ver</a>}
                      <a href={documentUrl(d.id, false)}>Descargar</a>
                      <button className="peligro" onClick={() => setBorrando(d)}>Borrar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <ConfirmDialog
        open={borrando !== null}
        titulo={`¿Borrar el documento «${borrando?.nombre ?? ''}»?`}
        mensaje="No se puede deshacer."
        confirmar="Borrar"
        onConfirm={confirmarBorrado}
        onCancel={() => setBorrando(null)}
      />
    </main>
  )
}
