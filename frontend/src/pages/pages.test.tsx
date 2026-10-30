/**
 * Tests de las pantallas (Login, Home) y del guardia de sesión de App.
 *
 * Para qué: comprobar lo que ve el usuario: error bajo el botón al fallar el login, botón
 * desactivado con campos vacíos, saludo y cierre de sesión en orden (primero el servidor, luego
 * la pantalla), y que los errores de la bbdd se muestran y no se arrastran tras un login correcto.
 * El cliente de API se simula (vi.mock), así que no hace falta backend.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'
import { ApiError, login, logout, me } from '../api/client'
import Home from './Home'
import Login from './Login'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
}))

beforeEach(() => vi.clearAllMocks())

describe('Login', () => {
  it('muestra el error de la API bajo el botón', async () => {
    vi.mocked(login).mockRejectedValue(new ApiError(401, 'Usuario o contraseña incorrectos'))
    render(<Login onLogin={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Usuario'), 'admin')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'mala')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Usuario o contraseña incorrectos')
  })

  it('deshabilita Entrar con los campos vacíos', () => {
    render(<Login onLogin={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Entrar' })).toBeDisabled()
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
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Base de datos no disponible')
  })

  it('no arrastra el error de me() tras login y logout', async () => {
    vi.mocked(me).mockRejectedValue(new ApiError(503, 'Base de datos no disponible'))
    vi.mocked(login).mockResolvedValue({ username: 'admin' })
    vi.mocked(logout).mockResolvedValue()
    render(<MemoryRouter><App /></MemoryRouter>)
    await screen.findByRole('alert')
    await userEvent.type(screen.getByLabelText('Usuario'), 'admin')
    await userEvent.type(screen.getByLabelText('Contraseña'), 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Cerrar sesión' }))
    await screen.findByLabelText('Usuario')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
