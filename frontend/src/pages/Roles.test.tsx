/**
 * Tests de la pantalla de gestión de roles (issue #5).
 *
 * Para qué: comprobar lo que ve el administrador: el listado con el número de usuarios, crear,
 * editar o renombrar, borrar con confirmación (y que no se borra si se cancela), la tabla de
 * usuarios al pulsar un rol, y que los errores de la API (409, 403…) se muestran tal cual.
 *
 * El cliente de API se simula (vi.mock), así que no hace falta backend.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createRole, deleteRole, listRoles, roleUsers, updateRole, type Rol } from '../api/client'
import Roles from './Roles'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  listRoles: vi.fn(),
  createRole: vi.fn(),
  updateRole: vi.fn(),
  deleteRole: vi.fn(),
  roleUsers: vi.fn(),
}))

const TUTOR: Rol = { id: 1, nombre: 'Tutor', descripcion: 'Tutoriza prácticas', num_usuarios: 2 }
const ALUMNO: Rol = { id: 2, nombre: 'Alumno', descripcion: null, num_usuarios: 0 }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listRoles).mockResolvedValue([ALUMNO, TUTOR])
})

/** Fila de la tabla de roles que contiene el texto dado. */
const fila = async (texto: string) => (await screen.findByRole('button', { name: texto })).closest('tr') as HTMLElement

describe('Roles', () => {
  it('lista los roles con descripción y número de usuarios', async () => {
    render(<Roles />)
    const tutor = await fila('Tutor')
    expect(within(tutor).getByText('Tutoriza prácticas')).toBeInTheDocument()
    expect(within(tutor).getByText('2')).toBeInTheDocument()
    expect(within(await fila('Alumno')).getByText('—')).toBeInTheDocument()
  })

  it('sin roles muestra un aviso', async () => {
    vi.mocked(listRoles).mockResolvedValue([])
    render(<Roles />)
    expect(await screen.findByText(/Todavía no hay roles/)).toBeInTheDocument()
  })

  it('muestra el error si no se puede cargar el listado (p. ej. 403)', async () => {
    vi.mocked(listRoles).mockRejectedValue(new ApiError(403, 'Solo el administrador puede hacer esto'))
    render(<Roles />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Solo el administrador puede hacer esto')
  })

  it('crea un rol, vacía el formulario y recarga el listado', async () => {
    vi.mocked(createRole).mockResolvedValue({ id: 3, nombre: 'Coordinador', descripcion: null, num_usuarios: 0 })
    render(<Roles />)
    const form = screen.getByRole('form', { name: 'Nuevo rol' })
    expect(within(form).getByRole('button', { name: 'Crear rol' })).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Nombre'), 'Coordinador')
    await userEvent.type(within(form).getByLabelText('Descripción'), 'Coordina')
    await userEvent.click(within(form).getByRole('button', { name: 'Crear rol' }))
    expect(createRole).toHaveBeenCalledWith('Coordinador', 'Coordina')
    expect(listRoles).toHaveBeenCalledTimes(2)
    expect(within(form).getByLabelText('Nombre')).toHaveValue('')
  })

  it('un nombre repetido muestra el 409 y conserva lo escrito', async () => {
    vi.mocked(createRole).mockRejectedValue(new ApiError(409, 'Ya existe un rol con ese nombre'))
    render(<Roles />)
    const form = screen.getByRole('form', { name: 'Nuevo rol' })
    await userEvent.type(within(form).getByLabelText('Nombre'), 'Tutor')
    await userEvent.click(within(form).getByRole('button', { name: 'Crear rol' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe un rol con ese nombre')
    expect(within(form).getByLabelText('Nombre')).toHaveValue('Tutor')
  })

  it('edita y renombra un rol', async () => {
    vi.mocked(updateRole).mockResolvedValue({ ...TUTOR, nombre: 'Tutor académico' })
    render(<Roles />)
    await userEvent.click(within(await fila('Tutor')).getByRole('button', { name: 'Editar' }))
    const form = screen.getByRole('form', { name: 'Editar Tutor' })
    const nombre = within(form).getByLabelText('Nombre')
    expect(nombre).toHaveValue('Tutor')
    await userEvent.clear(nombre)
    await userEvent.type(nombre, 'Tutor académico')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    expect(updateRole).toHaveBeenCalledWith(1, 'Tutor académico', 'Tutoriza prácticas')
    expect(screen.queryByRole('form', { name: 'Editar Tutor' })).not.toBeInTheDocument()
  })

  it('cancelar la edición no llama a la API', async () => {
    render(<Roles />)
    await userEvent.click(within(await fila('Tutor')).getByRole('button', { name: 'Editar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(updateRole).not.toHaveBeenCalled()
    expect(await fila('Tutor')).toBeInTheDocument()
  })

  it('borra tras confirmar', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(deleteRole).mockResolvedValue()
    render(<Roles />)
    await userEvent.click(within(await fila('Alumno')).getByRole('button', { name: 'Borrar' }))
    expect(window.confirm).toHaveBeenCalledWith('¿Borrar el rol «Alumno»? No se puede deshacer.')
    expect(deleteRole).toHaveBeenCalledWith(2)
    expect(listRoles).toHaveBeenCalledTimes(2)
  })

  it('si se cancela la confirmación no borra', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<Roles />)
    await userEvent.click(within(await fila('Alumno')).getByRole('button', { name: 'Borrar' }))
    expect(deleteRole).not.toHaveBeenCalled()
  })

  it('borrar un rol con usuarios muestra el 409', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(deleteRole).mockRejectedValue(new ApiError(409, 'No se puede borrar: el rol está asignado a 2 usuarios'))
    render(<Roles />)
    await userEvent.click(within(await fila('Tutor')).getByRole('button', { name: 'Borrar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('asignado a 2 usuarios')
  })

  it('al pulsar un rol muestra la tabla de sus usuarios, y al pulsar otra vez la cierra', async () => {
    vi.mocked(roleUsers).mockResolvedValue([
      { id: 5, username: 'ana', email: null },
      { id: 7, username: 'pepe', email: 'pepe@example.com' },
    ])
    render(<Roles />)
    await userEvent.click(await screen.findByRole('button', { name: 'Tutor' }))
    expect(roleUsers).toHaveBeenCalledWith(1)
    const seccion = screen.getByRole('region', { name: 'Usuarios con el rol «Tutor»' })
    expect(await within(seccion).findByText('pepe@example.com')).toBeInTheDocument()
    expect(within(seccion).getByText('ana')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tutor' }))
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })

  it('un rol sin usuarios lo dice', async () => {
    vi.mocked(roleUsers).mockResolvedValue([])
    render(<Roles />)
    await userEvent.click(await screen.findByRole('button', { name: 'Alumno' }))
    expect(await screen.findByText('Ningún usuario tiene este rol.')).toBeInTheDocument()
  })
})
