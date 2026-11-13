/**
 * Tests de las pantallas (Login, ResetPassword, Home), del menú (Layout) y del guardia de sesión de App.
 *
 * Para qué: comprobar lo que ve el usuario: error bajo el botón al fallar el login, botón
 * desactivado con campos vacíos o sin captcha, el captcha se envía y se reinicia tras un fallo,
 * el logo solo en las pantallas sin sesión, el enlace al reseteo, saludo y cierre de sesión en
 * orden (primero el servidor, luego la pantalla), que los errores de la bbdd se muestran y no
 * se arrastran tras un login correcto, y que las entradas «Usuarios» y «Roles» y sus rutas son
 * solo para el administrador.
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
import { ApiError, listProjects, listRoles, listUsers, login, logout, me, resetPassword } from '../api/client'
import Layout from '../components/Layout'
import Home from './Home'
import Login from './Login'
import ResetPassword from './ResetPassword'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
  resetPassword: vi.fn(),
  listRoles: vi.fn(),
  listProjects: vi.fn(),
  listUsers: vi.fn(),
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

const ADMIN = { username: 'admin', es_admin: true }
const PEPE = { username: 'pepe', es_admin: false }

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
    vi.mocked(login).mockResolvedValue(ADMIN)
    const onLogin = vi.fn()
    inRouter(<Login onLogin={onLogin} />)
    await fillLogin('admin', 'secreto')
    expect(login).toHaveBeenCalledWith('admin', 'secreto', 'captcha-1')
    expect(onLogin).toHaveBeenCalledWith(ADMIN)
  })

  it('tras un fallo pide un reto nuevo y obliga a resolverlo otra vez', async () => {
    vi.mocked(login).mockRejectedValueOnce(new ApiError(401, 'Usuario o contraseña incorrectos'))
    vi.mocked(login).mockResolvedValueOnce(ADMIN)
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
  it('saluda al usuario', () => {
    render(<Home username="admin" />)
    expect(screen.getByText('Hola, admin')).toBeInTheDocument()
  })
})

describe('Layout (menú)', () => {
  it('cierra sesión: primero el servidor, luego la pantalla', async () => {
    vi.mocked(logout).mockResolvedValue()
    const onLogout = vi.fn()
    inRouter(<Layout user={ADMIN} onLogout={onLogout} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(logout).toHaveBeenCalled()
    expect(onLogout).toHaveBeenCalled()
    expect(vi.mocked(logout).mock.invocationCallOrder[0]).toBeLessThan(onLogout.mock.invocationCallOrder[0])
  })

  it('muestra el error si logout falla y no llama a onLogout', async () => {
    vi.mocked(logout).mockRejectedValue(new ApiError(503, 'Base de datos no disponible'))
    const onLogout = vi.fn()
    inRouter(<Layout user={ADMIN} onLogout={onLogout} />)
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Base de datos no disponible')
    expect(onLogout).not.toHaveBeenCalled()
  })

  it('el administrador ve las entradas «Usuarios» y «Roles»', () => {
    inRouter(<Layout user={ADMIN} onLogout={vi.fn()} />)
    expect(screen.getByRole('link', { name: 'Usuarios' })).toHaveAttribute('href', '/usuarios')
    expect(screen.getByRole('link', { name: 'Roles' })).toHaveAttribute('href', '/roles')
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('un usuario normal no ve «Usuarios» ni «Roles»', () => {
    inRouter(<Layout user={PEPE} onLogout={vi.fn()} />)
    expect(screen.getByRole('link', { name: 'Inicio' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Usuarios' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Roles' })).not.toBeInTheDocument()
  })

  it('«Usuarios» sigue marcado en el detalle de un usuario', () => {
    inRouter(<Layout user={ADMIN} onLogout={vi.fn()} />, '/usuarios/5')
    expect(screen.getByRole('link', { name: 'Usuarios' })).toHaveClass('active')
    expect(screen.getByRole('link', { name: 'Inicio' })).not.toHaveClass('active')
  })

  it('la entrada «Proyectos» solo la ve el administrador', () => {
    const { unmount } = inRouter(<Layout user={ADMIN} onLogout={vi.fn()} />)
    expect(screen.getByRole('link', { name: 'Proyectos' })).toHaveAttribute('href', '/proyectos')
    unmount()
    inRouter(<Layout user={PEPE} onLogout={vi.fn()} />)
    expect(screen.queryByRole('link', { name: 'Proyectos' })).not.toBeInTheDocument()
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
    vi.mocked(login).mockResolvedValue(ADMIN)
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
    vi.mocked(me).mockResolvedValue(ADMIN)
    inRouter(<App />)
    await screen.findByText('Hola, admin')
    expect(screen.queryByRole('img', { name: 'CDS' })).not.toBeInTheDocument()
  })

  it('con sesión, /reset-password redirige a la home', async () => {
    vi.mocked(me).mockResolvedValue(ADMIN)
    inRouter(<App />, '/reset-password')
    expect(await screen.findByText('Hola, admin')).toBeInTheDocument()
  })

  it('el administrador llega a /roles desde el menú', async () => {
    vi.mocked(me).mockResolvedValue(ADMIN)
    vi.mocked(listRoles).mockResolvedValue([])
    inRouter(<App />)
    await userEvent.click(await screen.findByRole('link', { name: 'Roles' }))
    expect(await screen.findByRole('heading', { name: 'Roles' })).toBeInTheDocument()
  })

  it('un usuario normal que escribe /roles a mano vuelve a la home', async () => {
    vi.mocked(me).mockResolvedValue(PEPE)
    inRouter(<App />, '/roles')
    expect(await screen.findByText('Hola, pepe')).toBeInTheDocument()
    expect(listRoles).not.toHaveBeenCalled()
  })

  it('el administrador llega a /usuarios desde el menú', async () => {
    vi.mocked(me).mockResolvedValue(ADMIN)
    vi.mocked(listUsers).mockResolvedValue([])
    inRouter(<App />)
    await userEvent.click(await screen.findByRole('link', { name: 'Usuarios' }))
    expect(await screen.findByRole('heading', { name: 'Usuarios' })).toBeInTheDocument()
  })

  it('un usuario normal que escribe /usuarios a mano vuelve a la home', async () => {
    vi.mocked(me).mockResolvedValue(PEPE)
    inRouter(<App />, '/usuarios/1')
    expect(await screen.findByText('Hola, pepe')).toBeInTheDocument()
    expect(listUsers).not.toHaveBeenCalled()
  })

  it('sin sesión, /roles lleva al login', async () => {
    vi.mocked(me).mockResolvedValue(null)
    inRouter(<App />, '/roles')
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument()
  })

  it('el administrador llega a /proyectos desde el menú', async () => {
    vi.mocked(me).mockResolvedValue(ADMIN)
    vi.mocked(listProjects).mockResolvedValue([])
    inRouter(<App />)
    await userEvent.click(await screen.findByRole('link', { name: 'Proyectos' }))
    expect(await screen.findByRole('heading', { name: 'Proyectos' })).toBeInTheDocument()
  })

  it('un usuario normal que escribe /proyectos o /proyectos/1 a mano vuelve a la home', async () => {
    vi.mocked(me).mockResolvedValue(PEPE)
    const { unmount } = inRouter(<App />, '/proyectos')
    expect(await screen.findByText('Hola, pepe')).toBeInTheDocument()
    unmount()
    inRouter(<App />, '/proyectos/1')
    expect(await screen.findByText('Hola, pepe')).toBeInTheDocument()
    expect(listProjects).not.toHaveBeenCalled()
  })
})
