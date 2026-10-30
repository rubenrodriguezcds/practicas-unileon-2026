import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, login, me } from './client'

const reply = (status: number, body?: unknown) =>
  vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  )

afterEach(() => vi.unstubAllGlobals())

describe('client', () => {
  it('login hace POST con JSON y devuelve el usuario', async () => {
    const fetchMock = reply(200, { username: 'admin' })
    vi.stubGlobal('fetch', fetchMock)
    await expect(login('admin', 'x')).resolves.toEqual({ username: 'admin' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ username: 'admin', password: 'x' })
  })

  it('login con 401 lanza ApiError con el detail', async () => {
    vi.stubGlobal('fetch', reply(401, { detail: 'Usuario o contraseña incorrectos' }))
    const err = await login('a', 'b').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe('Usuario o contraseña incorrectos')
    expect(err.status).toBe(401)
  })

  it('me con 401 devuelve null', async () => {
    vi.stubGlobal('fetch', reply(401, { detail: 'No autenticado' }))
    await expect(me()).resolves.toBeNull()
  })
})
