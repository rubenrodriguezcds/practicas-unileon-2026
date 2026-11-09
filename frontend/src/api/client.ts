/**
 * Cliente de la API: el ÚNICO fichero del frontend que hace peticiones al backend.
 *
 * Para qué: ofrece funciones simples (login, logout, me) que las pantallas llaman sin saber nada
 * de fetch, URLs ni códigos HTTP. Los errores llegan como ApiError con el mensaje del backend,
 * listo para enseñarlo al usuario.
 *
 * Por qué existe: centralizar la red en un sitio. Si cambia una ruta o el formato de la API, se
 * toca solo aquí.
 *
 * Notas: usa rutas relativas (/api/...), nunca un host. Así funciona igual con la API y el
 * frontend en el mismo contenedor (hoy) que separados detrás de nginx (en el futuro). La cookie
 * de sesión la envía el navegador solo porque frontend y API comparten origen.
 */

/**
 * Error devuelto por la API (respuesta no 2xx).
 * `message` es el `detail` del backend (o "Error inesperado") y se muestra tal cual al usuario;
 * `status` es el código HTTP, para que el código distinga casos como 401.
 */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/**
 * Envuelve `fetch` con cookies de sesión y cabecera JSON.
 * @throws {ApiError} si la respuesta no es 2xx, con el `detail` del cuerpo cuando existe.
 */
async function request(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? 'Error inesperado')
  }
  return res
}

/**
 * Inicia sesión con usuario y contraseña (POST /api/auth/login).
 * @returns el usuario autenticado.
 * @throws {ApiError} p. ej. 401 con "Usuario o contraseña incorrectos"; la pantalla Login muestra el mensaje.
 */
export async function login(username: string, password: string): Promise<{ username: string }> {
  const res = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  return res.json()
}

/**
 * Cierra la sesión (POST /api/auth/logout).
 * @throws {ApiError} si falla; Home muestra el mensaje y mantiene la sesión.
 */
export async function logout(): Promise<void> {
  await request('/api/auth/logout', { method: 'POST' })
}

/**
 * Consulta la sesión actual (GET /api/auth/me).
 * @returns el usuario, o `null` si no hay sesión (401), que es un caso normal y no un error.
 * @throws {ApiError} para cualquier otro fallo (p. ej. 503); App lo muestra en Login.
 */
export async function me(): Promise<{ username: string } | null> {
  try {
    return await (await request('/api/auth/me')).json()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null
    throw e
  }
}
