/**
 * Tests del cliente de API (client.ts) con fetch simulado.
 *
 * Para qué: comprobar que las peticiones salen con la forma que espera el backend (ruta, método,
 * JSON, captcha incluido) y que los errores se convierten bien: un 401 del login llega como ApiError con su
 * mensaje, y un 401 de me() significa «no hay sesión» (null), no un error.
 * No hace falta backend: fetch se sustituye por un doble.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError, addUserRole, createRole, createUser, deleteRole, deleteUser, deleteUsers, getUser, listRoles, listUsers, login, me,
  removeUserRole, resetPassword, roleUsers, updateRole, updateUser,
} from './client'

// Crea un `fetch` simulado que responde con el status y el cuerpo JSON dados.
const reply = (status: number, body?: unknown) =>
  vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  )

afterEach(() => vi.unstubAllGlobals())

describe('client', () => {
  it('login hace POST con JSON y devuelve el usuario', async () => {
    const fetchMock = reply(200, { username: 'admin' })
    vi.stubGlobal('fetch', fetchMock)
    await expect(login('admin', 'x', 'captcha')).resolves.toEqual({ username: 'admin' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ username: 'admin', password: 'x', altcha: 'captcha' })
  })

  it('login con 401 lanza ApiError con el detail', async () => {
    vi.stubGlobal('fetch', reply(401, { detail: 'Usuario o contraseña incorrectos' }))
    const err = await login('a', 'b', 'c').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe('Usuario o contraseña incorrectos')
    expect(err.status).toBe(401)
  })

  it('me con 401 devuelve null', async () => {
    vi.stubGlobal('fetch', reply(401, { detail: 'No autenticado' }))
    await expect(me()).resolves.toBeNull()
  })

  it('resetPassword hace POST con usuario y captcha y devuelve el mensaje', async () => {
    const fetchMock = reply(202, { detail: 'Si el usuario existe, recibirá un correo con una contraseña nueva.' })
    vi.stubGlobal('fetch', fetchMock)
    await expect(resetPassword('admin', 'captcha')).resolves.toEqual({
      detail: 'Si el usuario existe, recibirá un correo con una contraseña nueva.',
    })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/reset')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ username: 'admin', altcha: 'captcha' })
  })

  it('resetPassword con 429 lanza ApiError con el detail', async () => {
    vi.stubGlobal('fetch', reply(429, { detail: 'Demasiados intentos. Prueba más tarde.' }))
    const err = await resetPassword('a', 'c').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(429)
  })

  it('me devuelve también es_admin', async () => {
    vi.stubGlobal('fetch', reply(200, { username: 'admin', es_admin: true }))
    await expect(me()).resolves.toEqual({ username: 'admin', es_admin: true })
  })
})

describe('client: roles', () => {
  const ROL = { id: 1, nombre: 'Tutor', descripcion: null, num_usuarios: 0 }

  it('listRoles hace GET /api/roles', async () => {
    const fetchMock = reply(200, [ROL])
    vi.stubGlobal('fetch', fetchMock)
    await expect(listRoles()).resolves.toEqual([ROL])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/roles')
  })

  it('createRole hace POST con nombre y descripción', async () => {
    const fetchMock = reply(201, ROL)
    vi.stubGlobal('fetch', fetchMock)
    await expect(createRole('Tutor', '')).resolves.toEqual(ROL)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/roles')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ nombre: 'Tutor', descripcion: '' })
  })

  it('updateRole hace PUT /api/roles/{id}', async () => {
    const fetchMock = reply(200, ROL)
    vi.stubGlobal('fetch', fetchMock)
    await updateRole(1, 'Tutor', 'd')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/roles/1')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ nombre: 'Tutor', descripcion: 'd' })
  })

  it('deleteRole hace DELETE y acepta el 204 sin cuerpo', async () => {
    const fetchMock = reply(204)
    vi.stubGlobal('fetch', fetchMock)
    await expect(deleteRole(1)).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/roles/1')
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')
  })

  it('deleteRole con 409 lanza ApiError con el detail', async () => {
    vi.stubGlobal('fetch', reply(409, { detail: 'No se puede borrar: el rol está asignado a 1 usuario' }))
    const err = await deleteRole(1).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.message).toBe('No se puede borrar: el rol está asignado a 1 usuario')
  })

  it('roleUsers hace GET /api/roles/{id}/usuarios', async () => {
    const fetchMock = reply(200, [])
    vi.stubGlobal('fetch', fetchMock)
    await expect(roleUsers(3)).resolves.toEqual([])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/roles/3/usuarios')
  })
})

describe('client: usuarios', () => {
  const U = { id: 2, username: 'pepe', email: 'p@example.com', es_admin: false, num_roles: 0 }

  it('listUsers hace GET /api/usuarios', async () => {
    const fetchMock = reply(200, [U])
    vi.stubGlobal('fetch', fetchMock)
    await expect(listUsers()).resolves.toEqual([U])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/usuarios')
  })

  it('getUser hace GET /api/usuarios/{id}', async () => {
    const fetchMock = reply(200, { ...U, roles: [] })
    vi.stubGlobal('fetch', fetchMock)
    await getUser(2)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/usuarios/2')
  })

  it('createUser hace POST con usuario, email y es_admin', async () => {
    const fetchMock = reply(201, U)
    vi.stubGlobal('fetch', fetchMock)
    await expect(createUser('pepe', 'p@example.com', true)).resolves.toEqual(U)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/usuarios')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ username: 'pepe', email: 'p@example.com', es_admin: true })
  })

  it('createUser con 502 lanza ApiError con el detail', async () => {
    vi.stubGlobal('fetch', reply(502, { detail: 'No se ha podido enviar el correo' }))
    const err = await createUser('a', 'a@example.com', false).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(502)
  })

  it('updateUser hace PUT /api/usuarios/{id}', async () => {
    const fetchMock = reply(200, U)
    vi.stubGlobal('fetch', fetchMock)
    await updateUser(2, 'jose', '', false)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/usuarios/2')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ username: 'jose', email: '', es_admin: false })
  })

  it('deleteUser hace DELETE y acepta el 204', async () => {
    const fetchMock = reply(204)
    vi.stubGlobal('fetch', fetchMock)
    await expect(deleteUser(2)).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')
  })

  it('deleteUsers hace POST /api/usuarios/borrar con los ids', async () => {
    const fetchMock = reply(200, { borrados: 2 })
    vi.stubGlobal('fetch', fetchMock)
    await expect(deleteUsers([2, 3])).resolves.toEqual({ borrados: 2 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/usuarios/borrar')
    expect(JSON.parse(init.body)).toEqual({ ids: [2, 3] })
  })

  it('addUserRole hace PUT y removeUserRole DELETE sobre /api/usuarios/{id}/roles/{rolId}', async () => {
    const fetchMock = reply(204)
    vi.stubGlobal('fetch', fetchMock)
    await addUserRole(2, 10)
    await removeUserRole(2, 10)
    expect(fetchMock.mock.calls.map((c) => [c[0], c[1].method])).toEqual([
      ['/api/usuarios/2/roles/10', 'PUT'],
      ['/api/usuarios/2/roles/10', 'DELETE'],
    ])
  })
})
