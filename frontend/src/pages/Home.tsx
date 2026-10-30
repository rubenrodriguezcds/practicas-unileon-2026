import { useState } from 'react'
import { logout } from '../api/client'

export default function Home({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [error, setError] = useState('')

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
