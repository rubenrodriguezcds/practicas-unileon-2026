/**
 * Cliente de la API: el ÚNICO fichero del frontend que hace peticiones al backend.
 *
 * Para qué: ofrece funciones simples (login, logout, me, resetPassword y las de roles) que las pantallas llaman sin saber nada
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
 * Usuario de la sesión. `es_admin` decide si se enseña el menú de administración (la API lo
 * comprueba otra vez en cada petición: esconder el menú no protege nada por sí solo).
 */
export type User = { username: string; es_admin: boolean }

/** Rol tal como lo devuelve la API; `num_usuarios` es cuántos usuarios lo tienen. */
export type Rol = { id: number; nombre: string; descripcion: string | null; num_usuarios: number }

/** Usuario que tiene un rol (GET /api/roles/{id}/usuarios). */
export type UsuarioDeRol = { id: number; username: string; email: string | null }

/**
 * Envuelve `fetch` con cookies de sesión y cabecera JSON (salvo en subidas con FormData).
 * @throws {ApiError} si la respuesta no es 2xx, con el `detail` del cuerpo cuando existe.
 */
async function request(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    // Con FormData el navegador pone el Content-Type con su boundary; fijarlo a mano lo rompería.
    headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail ?? 'Error inesperado')
  }
  return res
}

/**
 * Inicia sesión con usuario, contraseña y captcha (POST /api/auth/login).
 * @param altcha payload del captcha resuelto (componente Captcha).
 * @returns el usuario autenticado y si es administrador.
 * @throws {ApiError} p. ej. 401 con "Usuario o contraseña incorrectos" o 400 con el captcha no
 *   válido; la pantalla Login muestra el mensaje.
 */
export async function login(username: string, password: string, altcha: string): Promise<User> {
  const res = await request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password, altcha }),
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
 * @returns el usuario (y si es administrador), o `null` si no hay sesión (401), que es un caso
 *   normal y no un error.
 * @throws {ApiError} para cualquier otro fallo (p. ej. 503); App lo muestra en Login.
 */
export async function me(): Promise<User | null> {
  try {
    return await (await request('/api/auth/me')).json()
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null
    throw e
  }
}

/**
 * Pide una contraseña nueva por correo (POST /api/auth/reset).
 * @returns el mensaje de la API, el mismo exista o no el usuario.
 * @throws {ApiError} 400 captcha no válido, 429 demasiados intentos; ResetPassword muestra el mensaje.
 */
export async function resetPassword(username: string, altcha: string): Promise<{ detail: string }> {
  const res = await request('/api/auth/reset', {
    method: 'POST',
    body: JSON.stringify({ username, altcha }),
  })
  return res.json()
}

// --- Roles (issue #5). Solo para el administrador: la API responde 403 a cualquier otro. ---

/** Todos los roles, por nombre (GET /api/roles). */
export async function listRoles(): Promise<Rol[]> {
  return (await request('/api/roles')).json()
}

/**
 * Crea un rol (POST /api/roles).
 * @throws {ApiError} 409 si el nombre ya existe; Roles muestra el mensaje.
 */
export async function createRole(nombre: string, descripcion: string): Promise<Rol> {
  const res = await request('/api/roles', { method: 'POST', body: JSON.stringify({ nombre, descripcion }) })
  return res.json()
}

/**
 * Renombra o edita un rol (PUT /api/roles/{id}).
 * @throws {ApiError} 404 si ya no existe; 409 si el nombre lo tiene otro rol.
 */
export async function updateRole(id: number, nombre: string, descripcion: string): Promise<Rol> {
  const res = await request(`/api/roles/${id}`, { method: 'PUT', body: JSON.stringify({ nombre, descripcion }) })
  return res.json()
}

/**
 * Borra un rol (DELETE /api/roles/{id}).
 * @throws {ApiError} 409 si algún usuario lo tiene (el mensaje dice cuántos); 404 si ya no existe.
 */
export async function deleteRole(id: number): Promise<void> {
  await request(`/api/roles/${id}`, { method: 'DELETE' })
}

/** Usuarios que tienen el rol (GET /api/roles/{id}/usuarios). */
export async function roleUsers(id: number): Promise<UsuarioDeRol[]> {
  return (await request(`/api/roles/${id}/usuarios`)).json()
}

// --- Proyectos y documentos (issue #7). Solo para el administrador: la API responde 403 a cualquier otro. ---

/** Proyecto del listado; `num_documentos` es cuántos documentos tiene adjuntos. */
export type Proyecto = { id: number; nombre: string; tipo: string | null; descripcion: string | null; num_documentos: number }

/** Documento adjunto a un proyecto; `tamano` en bytes y `visible` si el navegador puede mostrarlo. */
export type Documento = { id: number; nombre: string; tamano: number; visible: boolean }

/** Proyecto con sus documentos (GET /api/proyectos/{id}). */
export type ProyectoDetalle = Omit<Proyecto, 'num_documentos'> & { documentos: Documento[] }

/** Todos los proyectos (GET /api/proyectos). */
export async function listProjects(): Promise<Proyecto[]> {
  return (await request('/api/proyectos')).json()
}

/**
 * Crea un proyecto (POST /api/proyectos). Los textos van tal cual: la API recorta y guarda los vacíos como null.
 * @throws {ApiError} 409 si ya hay un proyecto con ese nombre; la pantalla muestra el mensaje.
 */
export async function createProject(p: { nombre: string; tipo: string; descripcion: string }): Promise<Proyecto> {
  const res = await request('/api/proyectos', { method: 'POST', body: JSON.stringify(p) })
  return res.json()
}

/**
 * Un proyecto con sus documentos (GET /api/proyectos/{id}).
 * @throws {ApiError} 404 si ya no existe.
 */
export async function getProject(id: number): Promise<ProyectoDetalle> {
  return (await request(`/api/proyectos/${id}`)).json()
}

/**
 * Borra un proyecto y sus documentos (DELETE /api/proyectos/{id}).
 * @throws {ApiError} 404 si ya no existe.
 */
export async function deleteProject(id: number): Promise<void> {
  await request(`/api/proyectos/${id}`, { method: 'DELETE' })
}

/**
 * Sube un documento a un proyecto (POST /api/proyectos/{id}/documentos, multipart con el campo `archivo`).
 * @throws {ApiError} 409 si ya hay uno con ese nombre en el proyecto; 413 si pasa del tamaño máximo.
 */
export async function uploadDocument(proyectoId: number, file: File): Promise<Omit<Documento, 'visible'>> {
  const body = new FormData()
  body.append('archivo', file)
  const res = await request(`/api/proyectos/${proyectoId}/documentos`, { method: 'POST', body })
  return res.json()
}

/**
 * Borra un documento (DELETE /api/documentos/{id}).
 * @throws {ApiError} 404 si ya no existe.
 */
export async function deleteDocument(id: number): Promise<void> {
  await request(`/api/documentos/${id}`, { method: 'DELETE' })
}

/** URL del documento: con `ver` se abre en el navegador (?ver=1) y sin él se descarga. */
export function documentUrl(id: number, ver: boolean): string {
  return `/api/documentos/${id}${ver ? '?ver=1' : ''}`
}
