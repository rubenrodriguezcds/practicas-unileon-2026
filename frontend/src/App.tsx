/**
 * Componente raíz: decide qué pantalla ve el usuario según tenga o no sesión.
 *
 * Para qué: define las rutas (/login → Login, /reset-password → ResetPassword, / → Home,
 * /roles → Roles) y hace de «guardia»: al cargar la página pregunta a la API (/api/auth/me) si ya
 * hay sesión, y redirige a /login o a / según la respuesta. Las pantallas con sesión van dentro de
 * Layout (menú superior).
 *
 * Por qué existe: la sesión vive en una cookie HttpOnly que el JavaScript no puede leer, así que
 * la única forma de saber si el usuario está dentro es preguntárselo al servidor.
 *
 * Quién lo usa: main.tsx. Usa las páginas de src/pages, components/Layout.tsx y el cliente de
 * src/api/client.ts.
 *
 * Notas: si /me falla por algo distinto de «no hay sesión» (p. ej. 503, bbdd caída) el mensaje
 * se muestra en el login en vez de tragárselo. /roles redirige a / si el usuario no es admin;
 * es solo comodidad: la API responde 403 de todos modos.
 */

import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { me, type User } from './api/client'
import Layout from './components/Layout'
import Home from './pages/Home'
import Login from './pages/Login'
import ResetPassword from './pages/ResetPassword'
import Roles from './pages/Roles'

/**
 * Componente raíz: guarda la sesión y decide qué pantalla mostrar.
 *
 * - Al montar llama a `me()`; mientras responde no pinta nada (evita parpadeo de /login).
 * - Sin sesión, `/` y `/roles` redirigen a `/login`; con sesión, `/login` y `/reset-password`
 *   redirigen a `/`. Cualquier otra ruta va a `/`.
 * - Si `me()` falla con algo distinto de 401 (p. ej. 503 por la base de datos), el mensaje se pasa a
 *   `Login` como `initialError` para que se muestre al usuario; se limpia al iniciar sesión.
 */
export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    me()
      .then((u) => setUser(u))
      .catch((e) => setError(e instanceof Error ? e.message : 'Error inesperado'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return null

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login onLogin={(u) => { setError(''); setUser(u) }} initialError={error} />} />
      <Route path="/reset-password" element={user ? <Navigate to="/" replace /> : <ResetPassword />} />
      <Route element={user ? <Layout user={user} onLogout={() => setUser(null)} /> : <Navigate to="/login" replace />}>
        <Route path="/" element={user && <Home username={user.username} />} />
        <Route path="/roles" element={user?.es_admin ? <Roles /> : <Navigate to="/" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
