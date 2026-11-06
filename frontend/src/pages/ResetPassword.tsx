/**
 * Pantalla «¿Olvidaste tu contraseña?» (/reset-password).
 *
 * Para qué: el usuario escribe su nombre de usuario, resuelve el captcha y la API le envía por
 * correo una contraseña nueva. La actual sigue valiendo hasta que entre con la nueva.
 *
 * Quién lo usa: App.tsx, en la ruta /reset-password (solo sin sesión). Se llega desde el enlace
 * de Login.
 *
 * Notas:
 *   - El mensaje de éxito es siempre el mismo, exista o no el usuario: lo decide la API para no
 *     revelar qué usuarios hay.
 *   - Tras cada envío (vaya bien o mal) el captcha se reinicia: cada reto vale una sola vez.
 */

import { useState, type SubmitEvent } from 'react'
import { Link } from 'react-router-dom'
import { resetPassword } from '../api/client'
import Captcha from '../components/Captcha'
import Logo from '../components/Logo'

export default function ResetPassword() {
  const [username, setUsername] = useState('')
  const [altcha, setAltcha] = useState<string | null>(null)
  const [captchaKey, setCaptchaKey] = useState(0)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  /** Pide el reseteo y muestra el mensaje de la API; reinicia el captcha en cualquier caso. */
  async function submit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage((await resetPassword(username, altcha ?? '')).detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error inesperado')
    }
    setAltcha(null)
    setCaptchaKey((k) => k + 1)
    setBusy(false)
  }

  return (
    <>
      <Logo />
      <main className="card">
        <form onSubmit={submit}>
          <h1>Recuperar contraseña</h1>
          <p className="hint">Te enviaremos una contraseña nueva al correo de tu cuenta.</p>
          <label>
            Usuario
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </label>
          <Captcha key={captchaKey} onChange={setAltcha} />
          <button type="submit" disabled={busy || !username || !altcha}>Enviar contraseña nueva</button>
          {message && <p role="status" className="ok">{message}</p>}
          {error && <p role="alert" className="error">{error}</p>}
          <Link to="/login" className="link">Volver a iniciar sesión</Link>
        </form>
      </main>
    </>
  )
}
