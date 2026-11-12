/**
 * Pantalla de gestión de usuarios (issue #6), solo para el administrador: alta y listado.
 *
 * Para qué: crear usuarios (la API genera la contraseña y la envía al email del usuario), ver el
 * listado con su email, si son administradores y cuántos roles tienen, y borrar varios a la vez
 * marcando sus casillas. Pulsando un usuario se va a su detalle (pages/UsuarioDetalle.tsx), donde
 * se edita, se borra y se gestionan sus roles.
 *
 * Quién lo usa: App.tsx, en la ruta /usuarios, solo si el usuario es administrador.
 *
 * Notas:
 *  - La casilla del propio administrador está desactivada: no puede borrarse a sí mismo (la API
 *    también lo impide con 409).
 *  - Borrar pide confirmación, porque no se puede deshacer.
 *  - Tras crear o borrar se vuelve a pedir el listado, para que siempre sea el del servidor.
 */

import { useEffect, useState, type SubmitEvent } from 'react'
import { Link } from 'react-router-dom'
import { createUser, deleteUsers, listUsers, type Usuario } from '../api/client'

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

/**
 * Alta y listado de usuarios.
 * @param props.yo nombre del usuario de la sesión (su fila no se puede marcar para borrar).
 */
export default function Usuarios({ yo }: { yo: string }) {
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null)
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [nuevo, setNuevo] = useState({ username: '', email: '', es_admin: false })
  const [marcados, setMarcados] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)

  const cargar = () => listUsers().then(setUsuarios).catch((err) => setError(mensaje(err)))

  useEffect(() => {
    listUsers().then(setUsuarios).catch((err) => setError(mensaje(err)))
  }, [])

  const borrables = (usuarios ?? []).filter((u) => u.username !== yo)
  const todosMarcados = borrables.length > 0 && borrables.every((u) => marcados.has(u.id))

  function marcar(id: number) {
    const s = new Set(marcados)
    if (s.has(id)) s.delete(id)
    else s.add(id)
    setMarcados(s)
  }

  async function crear(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setOk('')
    try {
      const u = await createUser(nuevo.username, nuevo.email, nuevo.es_admin)
      setOk(`Usuario «${u.username}» creado. Se le ha enviado la contraseña a ${u.email}.`)
      setNuevo({ username: '', email: '', es_admin: false })
      await cargar()
    } catch (err) {
      setError(mensaje(err))
    } finally {
      setBusy(false)
    }
  }

  async function borrarMarcados() {
    const n = marcados.size
    if (!window.confirm(`¿Borrar ${n === 1 ? '1 usuario' : `${n} usuarios`}? No se puede deshacer.`)) return
    setBusy(true)
    setError('')
    setOk('')
    try {
      const { borrados } = await deleteUsers([...marcados])
      setOk(borrados === 1 ? 'Se ha borrado 1 usuario.' : `Se han borrado ${borrados} usuarios.`)
      setMarcados(new Set())
      await cargar()
    } catch (err) {
      setError(mensaje(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="pagina">
      <h1>Usuarios</h1>

      <form className="fila" onSubmit={crear} aria-label="Nuevo usuario">
        <label>
          Usuario
          <input id="nuevo-usuario" value={nuevo.username} onChange={(e) => setNuevo({ ...nuevo, username: e.target.value })} maxLength={50} autoComplete="off" />
        </label>
        <label className="ancho">
          Email
          <input id="nuevo-email" type="email" value={nuevo.email} onChange={(e) => setNuevo({ ...nuevo, email: e.target.value })} maxLength={255} autoComplete="off" />
        </label>
        <label className="check">
          <input id="nuevo-admin" type="checkbox" checked={nuevo.es_admin} onChange={(e) => setNuevo({ ...nuevo, es_admin: e.target.checked })} />
          Administrador
        </label>
        <button type="submit" disabled={busy || !nuevo.username.trim() || !nuevo.email.trim()}>Crear usuario</button>
      </form>
      <p className="hint">La contraseña se genera sola y se envía al email del usuario.</p>

      {error && <p role="alert" className="error">{error}</p>}
      {ok && <p role="status" className="ok">{ok}</p>}

      {usuarios === null ? (
        !error && <p className="hint">Cargando…</p>
      ) : (
        <>
          <div className="barra-acciones">
            <button className="peligro" disabled={busy || marcados.size === 0} onClick={borrarMarcados}>
              Borrar seleccionados{marcados.size > 0 ? ` (${marcados.size})` : ''}
            </button>
          </div>
          <table>
            <thead>
              <tr>
                <th>
                  <input type="checkbox" aria-label="Seleccionar todos" checked={todosMarcados} disabled={borrables.length === 0}
                    onChange={() => setMarcados(todosMarcados ? new Set() : new Set(borrables.map((u) => u.id)))} />
                </th>
                <th>Usuario</th><th>Email</th><th>Administrador</th><th>Roles</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.map((u) => (
                <tr key={u.id} className={marcados.has(u.id) ? 'seleccionada' : undefined}>
                  <td>
                    <input type="checkbox" aria-label={`Seleccionar ${u.username}`} checked={marcados.has(u.id)}
                      disabled={u.username === yo} title={u.username === yo ? 'No puedes borrarte a ti mismo' : undefined}
                      onChange={() => marcar(u.id)} />
                  </td>
                  <td><Link to={`/usuarios/${u.id}`}>{u.username}</Link>{u.username === yo && <span className="hint"> (tú)</span>}</td>
                  <td>{u.email ?? '—'}</td>
                  <td>{u.es_admin ? 'Sí' : '—'}</td>
                  <td>{u.num_roles}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  )
}
