import { useState, type SubmitEvent } from 'react'
import { login } from '../api/client'

export default function Login({ onLogin, initialError = '' }: { onLogin: (username: string) => void; initialError?: string }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(initialError)
  const [busy, setBusy] = useState(false)

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
