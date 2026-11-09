/**
 * Pantalla principal para el usuario que ha iniciado sesión.
 *
 * Para qué: saluda al usuario y ofrece el botón «Cerrar sesión». Es el punto de partida donde
 * irán las funciones del gestor documental.
 *
 * Quién lo usa: App.tsx, en la ruta /, solo si hay sesión.
 *
 * Notas: al cerrar sesión primero se avisa al servidor (logout) y solo si responde bien se
 * vuelve al login; si falla, se muestra el error y el usuario sigue dentro, para que la pantalla
 * no diga «fuera» mientras el servidor aún tiene la sesión abierta.
 */

import { useState } from 'react'
import { logout } from '../api/client'

/**
 * Pantalla protegida con saludo y botón "Cerrar sesión".
 * @param props.username nombre a mostrar en el saludo.
 * @param props.onLogout se llama solo si `logout()` tuvo éxito (App entonces redirige a /login).
 * Si `logout()` falla, muestra el mensaje del error en un `role="alert"` y NO llama a `onLogout`.
 */
export default function Home({ username, onLogout }: { username: string; onLogout: () => void }) {
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
    <main className="card">
      <h1>Hola, {username}</h1>
      <button onClick={salir}>Cerrar sesión</button>
      {error && <p role="alert" className="error">{error}</p>}
    </main>
  )
}
