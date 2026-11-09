/**
 * Pantalla de inicio de sesión.
 *
 * Para qué: formulario de usuario, contraseña y captcha anti-bot, con el logo arriba a la izquierda
 * y el enlace «¿Olvidaste tu contraseña?». Al enviarlo llama a login() del cliente de API;
 * si va bien avisa a App (onLogin) para que lleve al usuario a la home, y si falla muestra el
 * mensaje del servidor bajo el botón («Usuario o contraseña incorrectos», «Base de datos no
 * disponible»…).
 *
 * Quién lo usa: App.tsx, en la ruta /login.
 *
 * Notas: el botón «Entrar» se desactiva con los campos vacíos, sin captcha resuelto o mientras
 * espera respuesta, para no enviar peticiones vacías ni duplicadas. Tras un fallo el captcha se
 * reinicia con un reto nuevo (cada reto vale una sola vez). El error usa role="alert" para que
 * los lectores de pantalla lo anuncien.
 */

import { useState, type SubmitEvent } from 'react'
import { Link } from 'react-router-dom'
import { login, type User } from '../api/client'
import Captcha from '../components/Captcha'
import Logo from '../components/Logo'

/**
 * Formulario de inicio de sesión.
 * @param props.onLogin se llama con el usuario devuelto por la API (nombre y si es admin) cuando el login es correcto.
 * @param props.initialError mensaje inicial a mostrar (App lo usa cuando `me()` falla por algo distinto de 401).
 * El botón "Entrar" se deshabilita con campos vacíos, sin captcha o con una petición en curso.
 * Si el login falla, el mensaje de la API se muestra en un `role="alert"` bajo el botón y el
 * captcha se vuelve a montar (`key`) para pedir un reto nuevo.
 */
export default function Login({ onLogin, initialError = '' }: { onLogin: (user: User) => void; initialError?: string }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(initialError)
  const [busy, setBusy] = useState(false)
  const [altcha, setAltcha] = useState<string | null>(null)
  const [captchaKey, setCaptchaKey] = useState(0)

  /** Envía las credenciales; ante error muestra el mensaje, reinicia el captcha y rehabilita el botón. */
  async function submit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      onLogin(await login(username, password, altcha ?? ''))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado')
      setAltcha(null)
      setCaptchaKey((k) => k + 1)
      setBusy(false)
    }
  }

  return (
    <>
      <Logo />
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
          <Captcha key={captchaKey} onChange={setAltcha} />
          <button type="submit" disabled={busy || !username || !password || !altcha}>Entrar</button>
          {error && <p role="alert" className="error">{error}</p>}
          <Link to="/reset-password" className="link">¿Olvidaste tu contraseña?</Link>
        </form>
      </main>
    </>
  )
}
