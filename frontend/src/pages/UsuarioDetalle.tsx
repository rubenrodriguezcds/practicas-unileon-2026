/**
 * Detalle de un usuario (issue #6), solo para el administrador.
 *
 * Para qué: editar o renombrar al usuario, cambiar su email, marcarlo o desmarcarlo como
 * administrador (casilla), borrarlo, y ver la tabla de sus roles para asociarle o quitarle roles.
 *
 * Quién lo usa: App.tsx, en la ruta /usuarios/:id, solo si el usuario es administrador. Se llega
 * pulsando un usuario en pages/Usuarios.tsx.
 *
 * Notas:
 *  - Si es el propio administrador, la casilla «Administrador» y «Borrar usuario» están
 *    desactivadas: no puede quitarse el permiso ni borrarse (la API también lo impide con 409).
 *  - Tras guardar se avisa a App (onCambio) para que el menú muestre el nombre nuevo si el
 *    administrador se ha renombrado a sí mismo.
 *  - El desplegable para añadir roles solo ofrece los que el usuario aún no tiene.
 */

import { useEffect, useState, type SubmitEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { addUserRole, deleteUser, getUser, listRoles, removeUserRole, updateUser, type Rol, type UsuarioDetalle as Detalle } from '../api/client'

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

/**
 * Detalle, edición y roles de un usuario.
 * @param props.yo nombre del usuario de la sesión (para no dejarle quitarse el permiso ni borrarse).
 * @param props.onCambio se llama tras guardar, para refrescar la sesión en App.
 */
export default function UsuarioDetalle({ yo, onCambio }: { yo: string; onCambio: () => void }) {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const [usuario, setUsuario] = useState<Detalle | null>(null)
  const [roles, setRoles] = useState<Rol[]>([])
  const [form, setForm] = useState({ username: '', email: '', es_admin: false })
  const [rolNuevo, setRolNuevo] = useState('')
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)

  function mostrar(u: Detalle) {
    setUsuario(u)
    setForm({ username: u.username, email: u.email ?? '', es_admin: u.es_admin })
  }

  useEffect(() => {
    getUser(id).then(mostrar).catch((err) => setError(mensaje(err)))
    listRoles().then(setRoles).catch((err) => setError(mensaje(err)))
  }, [id])

  const soyYo = usuario?.username === yo

  /** Ejecuta una acción; si va bien vuelve a pedir el usuario, si falla muestra el error. */
  async function accion(fn: () => Promise<unknown>, hecho: string) {
    setBusy(true)
    setError('')
    setOk('')
    try {
      await fn()
      mostrar(await getUser(id))
      setOk(hecho)
    } catch (err) {
      setError(mensaje(err))
    } finally {
      setBusy(false)
    }
  }

  async function guardar(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    await accion(() => updateUser(id, form.username, form.email, form.es_admin), 'Cambios guardados.')
    onCambio()
  }

  async function borrar() {
    if (!usuario || !window.confirm(`¿Borrar el usuario «${usuario.username}»? No se puede deshacer.`)) return
    setBusy(true)
    setError('')
    try {
      await deleteUser(id)
      navigate('/usuarios')
    } catch (err) {
      setError(mensaje(err))
      setBusy(false)
    }
  }

  async function anadirRol(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    const rol = roles.find((r) => r.id === Number(rolNuevo))
    if (!rol) return
    await accion(() => addUserRole(id, rol.id), `Rol «${rol.nombre}» añadido.`)
    setRolNuevo('')
  }

  if (!usuario) {
    return (
      <main className="pagina">
        <Link to="/usuarios">← Usuarios</Link>
        {error ? <p role="alert" className="error">{error}</p> : <p className="hint">Cargando…</p>}
      </main>
    )
  }

  const disponibles = roles.filter((r) => !usuario.roles.some((ur) => ur.id === r.id))

  return (
    <main className="pagina">
      <Link to="/usuarios">← Usuarios</Link>
      <h1>{usuario.username}{soyYo && <span className="hint"> (tú)</span>}</h1>

      <form className="fila" onSubmit={guardar} aria-label="Datos del usuario">
        <label>
          Usuario
          <input id="editar-usuario" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} maxLength={50} autoComplete="off" />
        </label>
        <label className="ancho">
          Email
          <input id="editar-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} maxLength={255} autoComplete="off" />
        </label>
        <label className="check" title={soyYo ? 'No puedes quitarte a ti mismo el permiso de administrador' : undefined}>
          <input id="editar-admin" type="checkbox" checked={form.es_admin} disabled={soyYo} onChange={(e) => setForm({ ...form, es_admin: e.target.checked })} />
          Administrador
        </label>
        <button type="submit" disabled={busy || !form.username.trim()}>Guardar</button>
      </form>
      {!form.email.trim() && <p className="hint">Sin email, el usuario no podrá recuperar su contraseña.</p>}

      {error && <p role="alert" className="error">{error}</p>}
      {ok && <p role="status" className="ok">{ok}</p>}

      <section aria-labelledby="roles-del-usuario">
        <h2 id="roles-del-usuario">Roles</h2>
        {usuario.roles.length === 0 ? (
          <p className="hint">Este usuario no tiene ningún rol.</p>
        ) : (
          <table>
            <thead><tr><th>Rol</th><th>Descripción</th><th><span className="oculto">Acciones</span></th></tr></thead>
            <tbody>
              {usuario.roles.map((r) => (
                <tr key={r.id}>
                  <td>{r.nombre}</td>
                  <td>{r.descripcion ?? '—'}</td>
                  <td className="acciones">
                    <button className="secundario" disabled={busy} aria-label={`Quitar ${r.nombre}`}
                      onClick={() => accion(() => removeUserRole(id, r.id), `Rol «${r.nombre}» quitado.`)}>
                      Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {roles.length === 0 ? (
          <p className="hint">Todavía no hay roles. Créalos en <Link to="/roles">Roles</Link>.</p>
        ) : disponibles.length > 0 && (
          <form className="fila" onSubmit={anadirRol} aria-label="Añadir rol">
            <label className="ancho">
              Añadir rol
              <select id="rol-nuevo" value={rolNuevo} onChange={(e) => setRolNuevo(e.target.value)}>
                <option value="">Elige un rol…</option>
                {disponibles.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
              </select>
            </label>
            <button type="submit" disabled={busy || !rolNuevo}>Añadir</button>
          </form>
        )}
      </section>

      <div className="barra-acciones">
        <button className="peligro" disabled={busy || soyYo} title={soyYo ? 'No puedes borrarte a ti mismo' : undefined} onClick={borrar}>
          Borrar usuario
        </button>
      </div>
    </main>
  )
}
