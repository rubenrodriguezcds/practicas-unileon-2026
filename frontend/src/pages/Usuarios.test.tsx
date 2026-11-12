/**
 * Tests de las pantallas de gestión de usuarios (issue #6): listado/alta y detalle.
 *
 * Para qué: comprobar lo que ve el administrador: el listado; crear (y el aviso de que la
 * contraseña va por correo); borrar en lote con confirmación, sin poder marcarse a sí mismo;
 * editar y renombrar; la casilla de administrador; borrar desde el detalle; asociar y quitar roles;
 * y que los errores de la API (409, 502…) se muestran tal cual.
 *
 * El cliente de API se simula (vi.mock), así que no hace falta backend.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import {
  ApiError, addUserRole, createUser, deleteUser, deleteUsers, getUser, listRoles, listUsers, removeUserRole, updateUser,
  type Usuario, type UsuarioDetalle as Detalle,
} from '../api/client'
import UsuarioDetalle from './UsuarioDetalle'
import Usuarios from './Usuarios'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  listUsers: vi.fn(), getUser: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(),
  deleteUsers: vi.fn(), addUserRole: vi.fn(), removeUserRole: vi.fn(), listRoles: vi.fn(),
}))

const ADMIN: Usuario = { id: 1, username: 'admin', email: null, es_admin: true, num_roles: 0 }
const PEPE: Usuario = { id: 2, username: 'pepe', email: 'pepe@example.com', es_admin: false, num_roles: 1 }
const ANA: Usuario = { id: 3, username: 'ana', email: null, es_admin: false, num_roles: 0 }
const TUTOR = { id: 10, nombre: 'Tutor', descripcion: 'Tutoriza', num_usuarios: 1 }
const ALUMNO = { id: 11, nombre: 'Alumno', descripcion: null, num_usuarios: 0 }
const PEPE_DETALLE: Detalle = { id: 2, username: 'pepe', email: 'pepe@example.com', es_admin: false,
  roles: [{ id: 10, nombre: 'Tutor', descripcion: 'Tutoriza' }] }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listUsers).mockResolvedValue([ADMIN, ANA, PEPE])
  vi.mocked(listRoles).mockResolvedValue([ALUMNO, TUTOR])
  vi.mocked(getUser).mockResolvedValue(PEPE_DETALLE)
})

const listado = () => render(<MemoryRouter><Usuarios yo="admin" /></MemoryRouter>)

function detalle(id = 2, onCambio = vi.fn()) {
  render(
    <MemoryRouter initialEntries={[`/usuarios/${id}`]}>
      <Routes>
        <Route path="/usuarios/:id" element={<UsuarioDetalle yo="admin" onCambio={onCambio} />} />
        <Route path="/usuarios" element={<p>Listado de usuarios</p>} />
      </Routes>
    </MemoryRouter>,
  )
  return onCambio
}

describe('Usuarios (listado y alta)', () => {
  it('lista los usuarios con su email, si son admin y su número de roles', async () => {
    listado()
    const fila = (await screen.findByRole('link', { name: 'pepe' })).closest('tr') as HTMLElement
    expect(within(fila).getByText('pepe@example.com')).toBeInTheDocument()
    expect(within(fila).getByText('1')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'pepe' })).toHaveAttribute('href', '/usuarios/2')
    expect(within(screen.getByRole('link', { name: 'admin' }).closest('tr') as HTMLElement).getByText('Sí')).toBeInTheDocument()
  })

  it('crea un usuario y avisa de que la contraseña va por correo', async () => {
    vi.mocked(createUser).mockResolvedValue({ id: 4, username: 'lucia', email: 'lucia@example.com', es_admin: true, num_roles: 0 })
    listado()
    const form = screen.getByRole('form', { name: 'Nuevo usuario' })
    const crear = within(form).getByRole('button', { name: 'Crear usuario' })
    expect(crear).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Usuario'), 'lucia')
    expect(crear).toBeDisabled() // falta el email
    await userEvent.type(within(form).getByLabelText('Email'), 'lucia@example.com')
    await userEvent.click(within(form).getByLabelText('Administrador'))
    await userEvent.click(crear)
    expect(createUser).toHaveBeenCalledWith('lucia', 'lucia@example.com', true)
    expect(await screen.findByRole('status')).toHaveTextContent('Se le ha enviado la contraseña a lucia@example.com')
    expect(within(form).getByLabelText('Usuario')).toHaveValue('')
    expect(listUsers).toHaveBeenCalledTimes(2)
  })

  it('si el correo falla muestra el 502 y conserva lo escrito', async () => {
    vi.mocked(createUser).mockRejectedValue(new ApiError(502, 'No se ha podido enviar el correo con la contraseña, así que el usuario no se ha creado.'))
    listado()
    const form = screen.getByRole('form', { name: 'Nuevo usuario' })
    await userEvent.type(within(form).getByLabelText('Usuario'), 'lucia')
    await userEvent.type(within(form).getByLabelText('Email'), 'lucia@example.com')
    await userEvent.click(within(form).getByRole('button', { name: 'Crear usuario' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('el usuario no se ha creado')
    expect(within(form).getByLabelText('Usuario')).toHaveValue('lucia')
  })

  it('no deja marcar al propio administrador', async () => {
    listado()
    expect(await screen.findByLabelText('Seleccionar admin')).toBeDisabled()
    expect(screen.getByLabelText('Seleccionar pepe')).toBeEnabled()
  })

  it('borra en lote tras confirmar', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(deleteUsers).mockResolvedValue({ borrados: 2 })
    listado()
    const borrar = await screen.findByRole('button', { name: /Borrar seleccionados/ })
    expect(borrar).toBeDisabled()
    await userEvent.click(screen.getByLabelText('Seleccionar pepe'))
    await userEvent.click(screen.getByLabelText('Seleccionar ana'))
    await userEvent.click(screen.getByRole('button', { name: 'Borrar seleccionados (2)' }))
    expect(window.confirm).toHaveBeenCalledWith('¿Borrar 2 usuarios? No se puede deshacer.')
    expect(vi.mocked(deleteUsers).mock.calls[0][0].sort()).toEqual([2, 3])
    expect(await screen.findByRole('status')).toHaveTextContent('Se han borrado 2 usuarios.')
  })

  it('«Seleccionar todos» marca a todos menos a uno mismo', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(deleteUsers).mockResolvedValue({ borrados: 2 })
    listado()
    await userEvent.click(await screen.findByLabelText('Seleccionar todos'))
    await userEvent.click(screen.getByRole('button', { name: 'Borrar seleccionados (2)' }))
    expect(vi.mocked(deleteUsers).mock.calls[0][0]).not.toContain(1)
  })

  it('si se cancela la confirmación no borra', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    listado()
    await userEvent.click(await screen.findByLabelText('Seleccionar pepe'))
    await userEvent.click(screen.getByRole('button', { name: 'Borrar seleccionados (1)' }))
    expect(deleteUsers).not.toHaveBeenCalled()
  })
})

describe('UsuarioDetalle', () => {
  it('muestra los datos y la tabla de roles', async () => {
    detalle()
    expect(await screen.findByRole('heading', { name: 'pepe' })).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveValue('pepe@example.com')
    expect(screen.getByLabelText('Administrador')).not.toBeChecked()
    const roles = screen.getByRole('region', { name: 'Roles' })
    expect(within(roles).getByText('Tutoriza')).toBeInTheDocument()
  })

  it('renombra, hace administrador y avisa a App para refrescar la sesión', async () => {
    vi.mocked(updateUser).mockResolvedValue({ ...PEPE, username: 'jose', es_admin: true })
    const onCambio = detalle()
    const nombre = await screen.findByLabelText('Usuario')
    await userEvent.clear(nombre)
    await userEvent.type(nombre, 'jose')
    await userEvent.click(screen.getByLabelText('Administrador'))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(updateUser).toHaveBeenCalledWith(2, 'jose', 'pepe@example.com', true)
    expect(await screen.findByRole('status')).toHaveTextContent('Cambios guardados.')
    expect(onCambio).toHaveBeenCalled()
  })

  it('un nombre repetido muestra el 409', async () => {
    vi.mocked(updateUser).mockRejectedValue(new ApiError(409, 'Ya existe un usuario con ese nombre'))
    detalle()
    await userEvent.click(await screen.findByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe un usuario con ese nombre')
  })

  it('en el propio administrador no se puede quitar el permiso ni borrar', async () => {
    vi.mocked(getUser).mockResolvedValue({ id: 1, username: 'admin', email: null, es_admin: true, roles: [] })
    detalle(1)
    expect(await screen.findByLabelText('Administrador')).toBeDisabled()
    expect(screen.getByLabelText('Administrador')).toBeChecked()
    expect(screen.getByRole('button', { name: 'Borrar usuario' })).toBeDisabled()
    expect(screen.getByText('Sin email, el usuario no podrá recuperar su contraseña.')).toBeInTheDocument()
  })

  it('borra tras confirmar y vuelve al listado', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(deleteUser).mockResolvedValue()
    detalle()
    await userEvent.click(await screen.findByRole('button', { name: 'Borrar usuario' }))
    expect(window.confirm).toHaveBeenCalledWith('¿Borrar el usuario «pepe»? No se puede deshacer.')
    expect(deleteUser).toHaveBeenCalledWith(2)
    expect(await screen.findByText('Listado de usuarios')).toBeInTheDocument()
  })

  it('añade un rol: el desplegable solo ofrece los que no tiene', async () => {
    vi.mocked(addUserRole).mockResolvedValue()
    detalle()
    const form = await screen.findByRole('form', { name: 'Añadir rol' })
    const select = within(form).getByLabelText('Añadir rol')
    expect(within(select).queryByRole('option', { name: 'Tutor' })).not.toBeInTheDocument()
    await userEvent.selectOptions(select, 'Alumno')
    vi.mocked(getUser).mockResolvedValue({ ...PEPE_DETALLE, roles: [...PEPE_DETALLE.roles, { id: 11, nombre: 'Alumno', descripcion: null }] })
    await userEvent.click(within(form).getByRole('button', { name: 'Añadir' }))
    expect(addUserRole).toHaveBeenCalledWith(2, 11)
    expect(await screen.findByRole('status')).toHaveTextContent('Rol «Alumno» añadido.')
    expect(screen.queryByRole('form', { name: 'Añadir rol' })).not.toBeInTheDocument() // ya los tiene todos
  })

  it('quita un rol', async () => {
    vi.mocked(removeUserRole).mockResolvedValue()
    detalle()
    vi.mocked(getUser).mockResolvedValue({ ...PEPE_DETALLE, roles: [] })
    await userEvent.click(await screen.findByRole('button', { name: 'Quitar Tutor' }))
    expect(removeUserRole).toHaveBeenCalledWith(2, 10)
    expect(await screen.findByText('Este usuario no tiene ningún rol.')).toBeInTheDocument()
  })

  it('si no hay roles creados, enlaza a la pantalla de roles', async () => {
    vi.mocked(listRoles).mockResolvedValue([])
    vi.mocked(getUser).mockResolvedValue({ ...PEPE_DETALLE, roles: [] })
    detalle()
    expect(await screen.findByRole('link', { name: 'Roles' })).toHaveAttribute('href', '/roles')
  })

  it('usuario inexistente muestra el 404', async () => {
    vi.mocked(getUser).mockRejectedValue(new ApiError(404, 'El usuario no existe'))
    detalle(99)
    expect(await screen.findByRole('alert')).toHaveTextContent('El usuario no existe')
  })
})
