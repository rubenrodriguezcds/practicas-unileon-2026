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
  ApiError, createProject, createRole, deleteDocument, deleteProject, deleteRole, documentUrl, getProject,
  listProjects, listRoles, login, me, resetPassword, roleUsers, updateProject, updateRole, uploadDocument,
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

describe('client: proyectos y documentos', () => {
  const PROYECTO = { id: 2, nombre: 'Web', tipo: null, descripcion: null, num_documentos: 0 }

  it('listProjects hace GET /api/proyectos', async () => {
    const fetchMock = reply(200, [PROYECTO])
    vi.stubGlobal('fetch', fetchMock)
    await expect(listProjects()).resolves.toEqual([PROYECTO])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/proyectos')
  })

  it('createProject manda nombre, tipo y descripción como JSON', async () => {
    const fetchMock = reply(201, PROYECTO)
    vi.stubGlobal('fetch', fetchMock)
    await createProject({ nombre: 'Web', tipo: '', descripcion: '' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/proyectos')
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ nombre: 'Web', tipo: '', descripcion: '' })
  })

  it('updateProject manda nombre, tipo y descripción con PUT', async () => {
    const fetchMock = reply(200, PROYECTO)
    vi.stubGlobal('fetch', fetchMock)
    await updateProject(1, { nombre: 'Web', tipo: 'Interno', descripcion: '' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/proyectos/1')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ nombre: 'Web', tipo: 'Interno', descripcion: '' })
  })

  it('createProject con 409 lanza ApiError con el detail', async () => {
    vi.stubGlobal('fetch', reply(409, { detail: 'Ya existe un proyecto con ese nombre' }))
    const err = await createProject({ nombre: 'Web', tipo: '', descripcion: '' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.message).toBe('Ya existe un proyecto con ese nombre')
  })

  it('getProject hace GET /api/proyectos/{id}', async () => {
    const detalle = { id: 2, nombre: 'Web', tipo: null, descripcion: null, documentos: [] }
    const fetchMock = reply(200, detalle)
    vi.stubGlobal('fetch', fetchMock)
    await expect(getProject(2)).resolves.toEqual(detalle)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/proyectos/2')
  })

  it('deleteProject y deleteDocument hacen DELETE y aceptan el 204', async () => {
    const fetchMock = reply(204)
    vi.stubGlobal('fetch', fetchMock)
    await expect(deleteProject(2)).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/proyectos/2')
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(deleteDocument(7)).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[1][0]).toBe('/api/documentos/7')
    expect(fetchMock.mock.calls[1][1].method).toBe('DELETE')
  })

  it('uploadDocument envía FormData con el archivo y sin Content-Type', async () => {
    const doc = { id: 9, nombre: 'a.pdf', tamano: 3, visible: false }
    const fetchMock = reply(201, doc)
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['abc'], 'a.pdf', { type: 'application/pdf' })
    await expect(uploadDocument(3, file)).resolves.toEqual(doc)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/proyectos/3/documentos')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('archivo')).toBe(file)
    expect(init.headers['Content-Type']).toBeUndefined()
  })

  it('documentUrl añade ?ver=1 solo para verlo en el navegador', () => {
    expect(documentUrl(5, true)).toBe('/api/documentos/5?ver=1')
    expect(documentUrl(5, false)).toBe('/api/documentos/5')
  })
})
