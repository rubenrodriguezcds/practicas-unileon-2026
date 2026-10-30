import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { me } from './api/client'
import Home from './pages/Home'
import Login from './pages/Login'

export default function App() {
  const [user, setUser] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    me()
      .then((u) => setUser(u?.username ?? null))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error inesperado'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return null

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login onLogin={(u) => { setError(''); setUser(u) }} initialError={error} />} />
      <Route path="/" element={user ? <Home username={user} onLogout={() => setUser(null)} /> : <Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
