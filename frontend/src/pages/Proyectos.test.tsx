/**
 * Tests de las pantallas de gestión de proyectos (issue #7): listado/alta y detalle con documentos.
 *
 * Para qué: comprobar lo que ve el administrador: el listado con el número de documentos, crear un
 * proyecto (y ver el 409 de nombre repetido), borrar con el aviso que dice cuántos documentos se
 * borran (y que cancelar no borra), y en el detalle: la tabla de documentos con tamaño legible,
 * «Ver» solo en los que se pueden ver, «Descargar», borrar documentos y subir varios archivos
 * arrastrándolos, cada uno con su estado (subido o el error de la API), sin subir los de más de 50 MB.
 *
 * El cliente de API se simula (vi.mock), así que no hace falta backend. jsdom no implementa
 * showModal()/close() del <dialog>: se simulan con el atributo `open`.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import {
  ApiError, createProject, deleteDocument, deleteProject, getProject, listProjects, uploadDocument,
  type Proyecto, type ProyectoDetalle,
} from '../api/client'
import ProyectoDetallePage from './ProyectoDetalle'
import Proyectos from './Proyectos'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  listProjects: vi.fn(),
  createProject: vi.fn(),
  getProject: vi.fn(),
  deleteProject: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})

const WEB: Proyecto = { id: 1, nombre: 'Web', tipo: 'Interno', descripcion: 'La web', num_documentos: 3 }
const APP: Proyecto = { id: 2, nombre: 'App', tipo: null, descripcion: null, num_documentos: 0 }
const DETALLE: ProyectoDetalle = {
  id: 1, nombre: 'Web', tipo: 'Interno', descripcion: 'La web del proyecto',
  documentos: [
    { id: 10, nombre: 'a.pdf', tamano: 2048, visible: true },
    { id: 11, nombre: 'b.docx', tamano: 500, visible: false },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listProjects).mockResolvedValue([APP, WEB])
  vi.mocked(getProject).mockResolvedValue(DETALLE)
})

const archivo = (nombre: string, tamano?: number) => {
  const f = new File(['x'], nombre)
  if (tamano !== undefined) Object.defineProperty(f, 'size', { value: tamano })
  return f
}

const verListado = () => render(<MemoryRouter><Proyectos /></MemoryRouter>)
const verDetalle = () => render(
  <MemoryRouter initialEntries={['/proyectos/1']}>
    <Routes><Route path="/proyectos/:id" element={<ProyectoDetallePage />} /></Routes>
  </MemoryRouter>,
)

/** Suelta archivos sobre la zona de arrastrar. */
const soltar = async (...files: File[]) =>
  fireEvent.drop(await screen.findByText(/Arrastra aquí los archivos/), { dataTransfer: { files } })

/** Fila de la tabla que contiene el texto dado. */
const fila = async (texto: string) => (await screen.findByText(texto)).closest('tr') as HTMLElement

describe('Proyectos (listado)', () => {
  it('lista los proyectos con enlace al detalle, tipo y número de documentos', async () => {
    verListado()
    const web = await fila('Web')
    expect(within(web).getByRole('link', { name: 'Web' })).toHaveAttribute('href', '/proyectos/1')
    expect(within(web).getByText('Interno')).toBeInTheDocument()
    expect(within(web).getByText('3')).toBeInTheDocument()
    expect(within(await fila('App')).getByText('—')).toBeInTheDocument()
  })

  it('sin proyectos muestra un aviso', async () => {
    vi.mocked(listProjects).mockResolvedValue([])
    verListado()
    expect(await screen.findByText(/Todavía no hay proyectos/)).toBeInTheDocument()
  })

  it('crea un proyecto y recarga el listado', async () => {
    vi.mocked(createProject).mockResolvedValue({ ...APP, id: 3, nombre: 'Nuevo' })
    verListado()
    await screen.findByText('Web')
    await userEvent.type(screen.getByLabelText('Nombre'), 'Nuevo')
    await userEvent.type(screen.getByLabelText('Tipo'), 'Externo')
    await userEvent.click(screen.getByRole('button', { name: 'Crear proyecto' }))
    expect(createProject).toHaveBeenCalledWith({ nombre: 'Nuevo', tipo: 'Externo', descripcion: '' })
    await waitFor(() => expect(listProjects).toHaveBeenCalledTimes(2))
    expect(screen.getByLabelText('Nombre')).toHaveValue('')
  })

  it('«Crear proyecto» está desactivado con el nombre vacío', async () => {
    verListado()
    await screen.findByText('Web')
    expect(screen.getByRole('button', { name: 'Crear proyecto' })).toBeDisabled()
  })

  it('muestra el 409 de nombre repetido', async () => {
    vi.mocked(createProject).mockRejectedValue(new ApiError(409, 'Ya existe un proyecto con ese nombre'))
    verListado()
    await screen.findByText('Web')
    await userEvent.type(screen.getByLabelText('Nombre'), 'web')
    await userEvent.click(screen.getByRole('button', { name: 'Crear proyecto' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe un proyecto con ese nombre')
  })

  it('borrar avisa de cuántos documentos se borran y, al confirmar, borra y recarga', async () => {
    vi.mocked(deleteProject).mockResolvedValue()
    verListado()
    await userEvent.click(within(await fila('Web')).getByRole('button', { name: 'Borrar' }))
    const aviso = screen.getByRole('dialog')
    expect(aviso).toHaveTextContent('Se borrarán también sus 3 documentos')
    await userEvent.click(within(aviso).getByRole('button', { name: 'Borrar' }))
    expect(deleteProject).toHaveBeenCalledWith(1)
    await waitFor(() => expect(listProjects).toHaveBeenCalledTimes(2))
  })

  it('cancelar el aviso no borra nada', async () => {
    verListado()
    await userEvent.click(within(await fila('Web')).getByRole('button', { name: 'Borrar' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancelar' }))
    expect(deleteProject).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

describe('ProyectoDetalle', () => {
  it('muestra los datos y los documentos con tamaño legible, Ver y Descargar', async () => {
    verDetalle()
    expect(await screen.findByRole('heading', { name: 'Web' })).toBeInTheDocument()
    expect(screen.getByText('Interno')).toBeInTheDocument()
    expect(screen.getByText('La web del proyecto')).toBeInTheDocument()
    const pdf = await fila('a.pdf')
    expect(within(pdf).getByText('2 KB')).toBeInTheDocument()
    const ver = within(pdf).getByRole('link', { name: 'Ver' })
    expect(ver).toHaveAttribute('href', '/api/documentos/10?ver=1')
    expect(ver).toHaveAttribute('target', '_blank')
    expect(within(pdf).getByRole('link', { name: 'Descargar' })).toHaveAttribute('download')
    const docx = await fila('b.docx')
    expect(within(docx).queryByRole('link', { name: 'Ver' })).not.toBeInTheDocument()
    expect(within(docx).getByRole('link', { name: 'Descargar' })).toHaveAttribute('href', '/api/documentos/11')
  })

  it('proyecto inexistente muestra el error de la API', async () => {
    vi.mocked(getProject).mockRejectedValue(new ApiError(404, 'El proyecto no existe'))
    verDetalle()
    expect(await screen.findByRole('alert')).toHaveTextContent('El proyecto no existe')
  })

  it('una ruta con id no numérico dice que no existe sin llamar a la API', async () => {
    render(
      <MemoryRouter initialEntries={['/proyectos/abc']}>
        <Routes><Route path="/proyectos/:id" element={<ProyectoDetallePage />} /></Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('El proyecto no existe')
    expect(getProject).not.toHaveBeenCalled()
  })

  it('borra un documento tras confirmar', async () => {
    vi.mocked(deleteDocument).mockResolvedValue()
    verDetalle()
    await userEvent.click(within(await fila('a.pdf')).getByRole('button', { name: 'Borrar' }))
    const aviso = screen.getByRole('dialog')
    expect(aviso).toHaveTextContent('a.pdf')
    await userEvent.click(within(aviso).getByRole('button', { name: 'Borrar' }))
    expect(deleteDocument).toHaveBeenCalledWith(10)
    await waitFor(() => expect(getProject).toHaveBeenCalledTimes(2))
  })

  it('al soltar varios archivos sube cada uno y muestra su estado; si uno falla, los demás suben', async () => {
    vi.mocked(uploadDocument)
      .mockResolvedValueOnce({ id: 12, nombre: 'c.pdf', tamano: 1 })
      .mockRejectedValueOnce(new ApiError(409, 'Ya existe un documento con ese nombre en el proyecto'))
    verDetalle()
    await screen.findByText('a.pdf')
    const c = archivo('c.pdf')
    const d = archivo('a.pdf')
    await soltar(c, d)
    const estado = await screen.findByRole('list', { name: 'Subidas' })
    await waitFor(() => expect(within(estado).getByText(/c\.pdf/).closest('li')).toHaveTextContent('Subido'))
    expect(within(estado).getByText(/a\.pdf/).closest('li')).toHaveTextContent('Ya existe un documento con ese nombre en el proyecto')
    expect(uploadDocument).toHaveBeenNthCalledWith(1, 1, c)
    expect(uploadDocument).toHaveBeenNthCalledWith(2, 1, d)
    await waitFor(() => expect(getProject).toHaveBeenCalledTimes(2))
  })

  it('un archivo de más de 50 MB se avisa sin subirlo', async () => {
    verDetalle()
    await screen.findByText('a.pdf')
    await soltar(archivo('grande.pdf', 51 * 1024 * 1024))
    const estado = await screen.findByRole('list', { name: 'Subidas' })
    expect(within(estado).getByText(/grande\.pdf/).closest('li')).toHaveTextContent('El archivo pasa de 50 MB')
    expect(uploadDocument).not.toHaveBeenCalled()
  })

  it('los errores de la API (proyecto borrado, archivo vacío) se muestran en su fila', async () => {
    vi.mocked(uploadDocument)
      .mockRejectedValueOnce(new ApiError(422, 'El archivo está vacío'))
      .mockRejectedValueOnce(new ApiError(404, 'El proyecto no existe'))
    verDetalle()
    await screen.findByText('a.pdf')
    await soltar(archivo('vacio.pdf'), archivo('otro.pdf'))
    const estado = await screen.findByRole('list', { name: 'Subidas' })
    await waitFor(() => expect(within(estado).getByText(/otro\.pdf/).closest('li')).toHaveTextContent('El proyecto no existe'))
    expect(within(estado).getByText(/vacio\.pdf/).closest('li')).toHaveTextContent('El archivo está vacío')
  })
})
