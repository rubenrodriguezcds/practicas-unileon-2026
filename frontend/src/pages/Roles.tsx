/**
 * Pantalla de gestión de roles (issue #5), solo para el administrador.
 *
 * Para qué: listado de todos los roles con el número de usuarios de cada uno; crear, editar o
 * renombrar y borrar roles; y, al pulsar en un rol, la tabla de los usuarios que lo tienen.
 *
 * Quién lo usa: App.tsx, en la ruta /roles, solo si el usuario es administrador. Usa las
 * funciones de roles de src/api/client.ts.
 *
 * Notas:
 *  - Los mensajes de error son los de la API, tal cual («Ya existe un rol con ese nombre», «No se
 *    puede borrar: el rol está asignado a 2 usuarios»…), con role="alert".
 *  - Tras crear, editar o borrar se vuelve a pedir el listado: así los números de usuarios y el
 *    orden por nombre siempre son los del servidor.
 *  - Borrar pide confirmación, porque no se puede deshacer.
 */

import { useEffect, useState, type SubmitEvent } from 'react'
import { createRole, deleteRole, listRoles, roleUsers, updateRole, type Rol, type UsuarioDeRol } from '../api/client'

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

/** Gestión de roles: alta, listado con edición y borrado, y usuarios del rol seleccionado. */
export default function Roles() {
  const [roles, setRoles] = useState<Rol[] | null>(null)
  const [error, setError] = useState('')
  const [nuevo, setNuevo] = useState({ nombre: '', descripcion: '' })
  const [editando, setEditando] = useState<{ id: number; nombre: string; descripcion: string } | null>(null)
  const [seleccionado, setSeleccionado] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  /** Pide el listado a la API; un fallo se muestra como error. */
  const cargar = () => listRoles().then(setRoles).catch((err) => setError(mensaje(err)))

  useEffect(() => {
    listRoles().then(setRoles).catch((err) => setError(mensaje(err)))
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
    if (await accion(() => createRole(nuevo.nombre, nuevo.descripcion))) setNuevo({ nombre: '', descripcion: '' })
  }

  async function guardar(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!editando) return
    if (await accion(() => updateRole(editando.id, editando.nombre, editando.descripcion))) setEditando(null)
  }

  async function borrar(rol: Rol) {
    if (!window.confirm(`¿Borrar el rol «${rol.nombre}»? No se puede deshacer.`)) return
    if ((await accion(() => deleteRole(rol.id))) && seleccionado === rol.id) setSeleccionado(null)
  }

  const rolSeleccionado = roles?.find((r) => r.id === seleccionado)

  return (
    <main className="pagina">
      <h1>Roles</h1>

      <form className="fila" onSubmit={crear} aria-label="Nuevo rol">
        <label>
          Nombre
          <input value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} maxLength={100} />
        </label>
        <label className="ancho">
          Descripción
          <input value={nuevo.descripcion} onChange={(e) => setNuevo({ ...nuevo, descripcion: e.target.value })} maxLength={500} />
        </label>
        <button type="submit" disabled={busy || !nuevo.nombre.trim()}>Crear rol</button>
      </form>

      {error && <p role="alert" className="error">{error}</p>}

      {roles === null ? (
        !error && <p className="hint">Cargando…</p>
      ) : roles.length === 0 ? (
        <p className="hint">Todavía no hay roles. Crea el primero con el formulario de arriba.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Nombre</th><th>Descripción</th><th>Usuarios</th><th><span className="oculto">Acciones</span></th></tr>
          </thead>
          <tbody>
            {roles.map((rol) =>
              editando?.id === rol.id ? (
                <tr key={rol.id}>
                  <td colSpan={4}>
                    <form className="fila" onSubmit={guardar} aria-label={`Editar ${rol.nombre}`}>
                      <label>
                        Nombre
                        <input value={editando.nombre} onChange={(e) => setEditando({ ...editando, nombre: e.target.value })} maxLength={100} autoFocus />
                      </label>
                      <label className="ancho">
                        Descripción
                        <input value={editando.descripcion} onChange={(e) => setEditando({ ...editando, descripcion: e.target.value })} maxLength={500} />
                      </label>
                      <button type="submit" disabled={busy || !editando.nombre.trim()}>Guardar</button>
                      <button type="button" className="secundario" onClick={() => setEditando(null)}>Cancelar</button>
                    </form>
                  </td>
                </tr>
              ) : (
                <tr key={rol.id} className={rol.id === seleccionado ? 'seleccionada' : undefined}>
                  <td>
                    <button className="enlace" aria-pressed={rol.id === seleccionado} onClick={() => setSeleccionado(rol.id === seleccionado ? null : rol.id)}>
                      {rol.nombre}
                    </button>
                  </td>
                  <td>{rol.descripcion ?? '—'}</td>
                  <td>{rol.num_usuarios}</td>
                  <td className="acciones">
                    <button className="secundario" disabled={busy}
                      onClick={() => { setError(''); setEditando({ id: rol.id, nombre: rol.nombre, descripcion: rol.descripcion ?? '' }) }}>
                      Editar
                    </button>
                    <button className="peligro" disabled={busy} onClick={() => borrar(rol)}>Borrar</button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}

      {/* key: al cambiar de rol, o si cambia su número de usuarios, se vuelve a montar y pide la lista otra vez */}
      {rolSeleccionado && <UsuariosDelRol key={`${rolSeleccionado.id}-${rolSeleccionado.num_usuarios}`} rol={rolSeleccionado} />}
    </main>
  )
}

/** Tabla de los usuarios que tienen el rol. */
function UsuariosDelRol({ rol }: { rol: Rol }) {
  const [usuarios, setUsuarios] = useState<UsuarioDeRol[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    roleUsers(rol.id).then(setUsuarios).catch((err) => setError(mensaje(err)))
  }, [rol.id])

  return (
    <section aria-labelledby="usuarios-del-rol">
      <h2 id="usuarios-del-rol">Usuarios con el rol «{rol.nombre}»</h2>
      {error ? (
        <p role="alert" className="error">{error}</p>
      ) : usuarios === null ? (
        <p className="hint">Cargando…</p>
      ) : usuarios.length === 0 ? (
        <p className="hint">Ningún usuario tiene este rol.</p>
      ) : (
        <table>
          <thead><tr><th>Usuario</th><th>Email</th></tr></thead>
          <tbody>
            {usuarios.map((u) => <tr key={u.id}><td>{u.username}</td><td>{u.email ?? '—'}</td></tr>)}
          </tbody>
        </table>
      )}
    </section>
  )
}
