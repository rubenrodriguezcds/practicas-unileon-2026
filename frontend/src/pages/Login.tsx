/**
 * Pantalla de inicio de sesión.
 *
 * Para qué: formulario de usuario y contraseña. Al enviarlo llama a login() del cliente de API;
 * si va bien avisa a App (onLogin) para que lleve al usuario a la home, y si falla muestra el
 * mensaje del servidor bajo el botón («Usuario o contraseña incorrectos», «Base de datos no
 * disponible»…).
 *
 * Quién lo usa: App.tsx, en la ruta /login.
 *
 * Notas: el botón «Entrar» se desactiva con los campos vacíos o mientras espera respuesta, para
 * no enviar peticiones vacías ni duplicadas. El error usa role="alert" para que los lectores de
 * pantalla lo anuncien.
 */

import { useState, type SubmitEvent } from 'react'
import { login } from '../api/client'

/**
 * Formulario de inicio de sesión.
 * @param props.onLogin se llama con el nombre de usuario devuelto por la API cuando el login es correcto.
 * @param props.initialError mensaje inicial a mostrar (App lo usa cuando `me()` falla por algo distinto de 401).
 * El botón "Entrar" se deshabilita con campos vacíos o mientras hay una petición en curso.
 * Si el login falla, el mensaje de la API se muestra en un `role="alert"` bajo el botón.
 */
export default function Login({ onLogin, initialError = '' }: { onLogin: (username: string) => void; initialError?: string }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(initialError)
  const [busy, setBusy] = useState(false)

  /** Envía las credenciales; ante error muestra el mensaje y rehabilita el botón. */
  async function submit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      onLogin((await login(username, password)).username)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado')
      setBusy(false)
    }
  }

  return (
    <main className="card">
      <form onSubmit={submit}>
        <h1>Iniciar sesión</h1>
        <label>
          Usuario
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label>
          Contraseña
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        <button type="submit" disabled={busy || !username || !password}>Entrar</button>
        {error && <p role="alert" className="error">{error}</p>}
      </form>
    </main>
  )
}
