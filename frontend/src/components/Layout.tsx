/**
 * Marco común de las pantallas con sesión: menú superior y, debajo, la pantalla de cada ruta.
 *
 * Para qué: el menú de navegación de la aplicación. Tiene «Inicio», «Usuarios» y «Roles» (solo para
 * el administrador), el nombre del usuario y «Cerrar sesión».
 *
 * Por qué existe: la issue #5 pide una entrada de menú para gestionar roles y hasta ahora no había
 * menú. Las próximas pantallas (usuarios, proyectos…) se añaden con una línea en `ENTRADAS`.
 *
 * Quién lo usa: App.tsx, como ruta padre de todas las pantallas con sesión (su contenido se
 * pinta en el <Outlet />).
 *
 * Notas: esconder «Roles» a quien no es admin es solo comodidad; quien protege es la API (403).
 * El cierre de sesión primero avisa al servidor y solo si responde bien sale de la pantalla; si
 * falla, muestra el error y el usuario sigue dentro, para que la pantalla no diga «fuera» mientras
 * el servidor aún tiene la sesión abierta.
 */

import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { logout, type User } from '../api/client'

/** Entradas del menú. `soloAdmin` las esconde a quien no es administrador. */
const ENTRADAS = [
  { to: '/', texto: 'Inicio', soloAdmin: false },
  { to: '/usuarios', texto: 'Usuarios', soloAdmin: true },
  { to: '/roles', texto: 'Roles', soloAdmin: true },
  { to: '/proyectos', texto: 'Proyectos', soloAdmin: true },
]

/**
 * Menú superior + pantalla de la ruta actual.
 * @param props.user usuario de la sesión (decide qué entradas se ven).
 * @param props.onLogout se llama solo si `logout()` tuvo éxito (App entonces redirige a /login).
 */
export default function Layout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [error, setError] = useState('')

  /** Cierra la sesión en el servidor y, solo si va bien, avisa al padre. */
  async function salir() {
    try {
      await logout()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado')
      return
    }
    onLogout()
  }

  return (
    <div className="app">
      <nav className="menu" aria-label="Menú principal">
        <ul>
          {ENTRADAS.filter((e) => !e.soloAdmin || user.es_admin).map((e) => (
            // `end` solo en Inicio: así «Usuarios» sigue marcado también en /usuarios/5
            <li key={e.to}><NavLink to={e.to} end={e.to === '/'}>{e.texto}</NavLink></li>
          ))}
        </ul>
        <span className="usuario">{user.username}</span>
        <button className="secundario" onClick={salir}>Cerrar sesión</button>
      </nav>
      {error && <p role="alert" className="error centrado">{error}</p>}
      <Outlet />
    </div>
  )
}
