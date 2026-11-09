/**
 * Tests de las pantallas (Login, ResetPassword, Home) y del guardia de sesión de App.
 *
 * Para qué: comprobar lo que ve el usuario: error bajo el botón al fallar el login, botón
 * desactivado con campos vacíos o sin captcha, el captcha se envía y se reinicia tras un fallo,
 * el logo solo en las pantallas sin sesión, el enlace al reseteo, saludo y cierre de sesión en
 * orden (primero el servidor, luego la pantalla), y que los errores de la bbdd se muestran y no
 * se arrastran tras un login correcto.
 *
 * El cliente de API se simula (vi.mock), así que no hace falta backend. El captcha real (un web
 * component que pide retos a la API) se sustituye por un botón «Resolver captcha» que entrega
 * un payload distinto en cada montaje: así se ve si se envía y si se ha pedido un reto nuevo.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import App from '../App'
import { ApiError, login, logout, me, resetPassword } from '../api/client'
import Home from './Home'
import Login from './Login'
import ResetPassword from './ResetPassword'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
  resetPassword: vi.fn(),
}))

// Cada montaje del captcha falso = un reto nuevo (captcha-1, captcha-2…).
let mounts = 0
vi.mock('../components/Captcha', async () => {
  const { useState } = await import('react')
  return {
    default: function FakeCaptcha({ onChange }: { onChange: (p: string | null) => void }) {
      const [n] = useState(() => ++mounts)
      return <button type="button" onClick={() => onChange(`captcha-${n}`)}>Resolver captcha</button>
    },
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  mounts = 0
})

const inRouter = (ui: ReactNode, path = '/') => render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>)

/** Rellena el login, resuelve el captcha y pulsa Entrar. */
async function fillLogin(user = 'admin', pass = 'x') {
  await userEvent.type(screen.getByLabelText('Usuario'), user)
  await userEvent.type(screen.getByLabelText('Contraseña'), pass)
  await userEvent.click(screen.getByRole('button', { name: 'Resolver captcha' }))
  await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
}

describe('Login', () => {
  it('muestra el error de la API bajo el botón', async () => {
    vi.mocked(login).mockRejectedValue(new ApiError(401, 'Usuario o contraseña incorrectos'))
    inRouter(<Login onLogin={vi.fn()} />)
    await fillLogin('admin', 'mala')
    expect(await screen.findByRole('alert')).toHaveTextContent('Usuario o contraseña incorrectos')
  })

  it('deshabilita Entrar con los campos vacíos', () => {
    inRouter(<Login onLogin={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeDisabled()
  })

  it('deshabilita Entrar sin captcha resuelto', async () => {
    inRouter(<Login onLogin={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Usuario'), 'admin')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'x')
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeDisabled()
  })

  it('envía el captcha con el login', async () => {
    vi.mocked(login).mockResolvedValue({ username: 'admin' })
    const onLogin = vi.fn()
    inRouter(<Login onLogin={onLogin} />)
    await fillLogin('admin', 'secreto')
    expect(login).toHaveBeenCalledWith('admin', 'secreto', 'captcha-1')
    expect(onLogin).toHaveBeenCalledWith('admin')
  })

  it('tras un fallo pide un reto nuevo y obliga a resolverlo otra vez', async () => {
    vi.mocked(login).mockRejectedValueOnce(new ApiError(401, 'Usuario o contraseña incorrectos'))
    vi.mocked(login).mockResolvedValueOnce({ username: 'admin' })
    inRouter(<Login onLogin={vi.fn()} />)
    await fillLogin('admin', 'mala')
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Resolver captcha' }))
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(vi.mocked(login).mock.calls[1][2]).toBe('captcha-2')
  })

  it('muestra el logo', () => {
    inRouter(<Login onLogin={vi.fn()} />)
    expect(screen.getByRole('img', { name: 'CDS' })).toHaveAttribute('src', '/cds-logo.png')
  })
})

describe('ResetPassword', () => {
  const MSG = 'Si el usuario existe, recibirá un correo con una contraseña nueva.'

  it('envía usuario y captcha, muestra el mensaje y pide un reto nuevo', async () => {
    vi.mocked(resetPassword).mockResolvedValue({ detail: MSG })
    inRouter(<ResetPassword />)
    expect(screen.getByRole('img', { name: 'CDS' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Usuario'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: 'Resolver captcha' }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar contraseña nueva' }))
    expect(resetPassword).toHaveBeenCalledWith('admin', 'captcha-1')
    expect(await screen.findByRole('status')).toHaveTextContent(MSG)
    expect(mounts).toBe(2)
    expect(screen.getByRole('button', { name: 'Enviar contraseña nueva' })).toBeDisabled()
  })

  it('muestra el error de la API (p. ej. 429) y pide un reto nuevo', async () => {
    vi.mocked(resetPassword).mockRejectedValue(new ApiError(429, 'Demasiados intentos. Prueba más tarde.'))
    inRouter(<ResetPassword />)
    await userEvent.type(screen.getByLabelText('Usuario'), 'admin')
    await userEvent.click(screen.getByRole('button', { name: 'Resolver captcha' }))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar contraseña nueva' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Demasiados intentos')
    expect(mounts).toBe(2)
  })
})

describe('Home', () => {
  it('saluda y cierra sesión', async () => {
    vi.mocked(logout).mockResolvedValue()
    const onLogout = vi.fn()
    render(<Home username="admin" onLogout={onLogout} />)
    expect(screen.getByText('Hola, admin')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(logout).toHaveBeenCalled()
    expect(onLogout).toHaveBeenCalled()
    expect(vi.mocked(logout).mock.invocationCallOrder[0]).toBeLessThan(onLogout.mock.invocationCallOrder[0])
  })

  it('muestra el error si logout falla y no llama a onLogout', async () => {
    vi.mocked(logout).mockRejectedValue(new ApiError(503, 'Base de datos no disponible'))
    const onLogout = vi.fn()
    render(<Home username="admin" onLogout={onLogout} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Base de datos no disponible')
    expect(onLogout).not.toHaveBeenCalled()
  })
})

// Cubre el guard de sesión: errores de me() distintos de 401 y que no se queden pegados tras logout.
describe('App', () => {
  it('muestra el error de me() distinto de 401', async () => {
    vi.mocked(me).mockRejectedValue(new ApiError(503, 'Base de datos no disponible'))
    inRouter(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Base de datos no disponible')
  })

  it('no arrastra el error de me() tras login y logout', async () => {
    vi.mocked(me).mockRejectedValue(new ApiError(503, 'Base de datos no disponible'))
    vi.mocked(login).mockResolvedValue({ username: 'admin' })
    vi.mocked(logout).mockResolvedValue()
    inRouter(<App />)
    await screen.findByRole('alert')
    await fillLogin()
    await userEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    await screen.findByLabelText('Usuario')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('el enlace «¿Olvidaste tu contraseña?» lleva a la pantalla de reseteo', async () => {
    vi.mocked(me).mockResolvedValue(null)
    inRouter(<App />, '/login')
    await userEvent.click(await screen.findByRole('link', { name: '¿Olvidaste tu contraseña?' }))
    expect(await screen.findByRole('heading', { name: 'Recuperar contraseña' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Volver a iniciar sesión' }))
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument()
  })

  it('el logo no aparece en la home (solo en login y reseteo)', async () => {
    vi.mocked(me).mockResolvedValue({ username: 'admin' })
    inRouter(<App />)
    await screen.findByText('Hola, admin')
    expect(screen.queryByRole('img', { name: 'CDS' })).not.toBeInTheDocument()
  })

  it('con sesión, /reset-password redirige a la home', async () => {
    vi.mocked(me).mockResolvedValue({ username: 'admin' })
    inRouter(<App />, '/reset-password')
    expect(await screen.findByText('Hola, admin')).toBeInTheDocument()
  })
})
