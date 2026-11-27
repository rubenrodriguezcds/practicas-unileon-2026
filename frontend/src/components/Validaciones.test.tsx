/**
 * Tests de la sección «Validación» de la ficha del proyecto.
 *
 * Para qué: comprobar lo que ve el director de proyectos: cada validación con su ✅/❌/⚠️, la
 * explicación y, al desplegar, todos los documentos donde aparece y el resumen de la IA; el resumen «N de M cumplen», añadir (con el error
 * de la API si el patrón no vale), editar, borrar con confirmación, validar una y «Validar todo»
 * de una en una con su progreso, siguiendo aunque una falle (p. ej. las de IA, aún no disponibles).
 *
 * El cliente de API se simula (vi.mock). jsdom no implementa showModal()/close() del <dialog>: se
 * simulan con el atributo `open`, como en Proyectos.test.tsx.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError, createValidation, deleteValidation, listValidations, runValidation, updateValidation, type Validacion,
} from '../api/client'
import Validaciones from './Validaciones'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  listValidations: vi.fn(),
  createValidation: vi.fn(),
  updateValidation: vi.fn(),
  deleteValidation: vi.fn(),
  runValidation: vi.fn(),
}))

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})

const VLAN: Validacion = {
  id: 1, proyecto_id: 7, nombre: 'Aparecen las VLAN', tipo: 'patron', criterio: '\\mVLAN\\s*\\d+', orden: 1,
  resultado: {
    estado: 'ok', explicacion: 'Aparece en 2 trozos de 1 documento', resumen: null, ejecutada: '2026-11-27T12:00:00+00:00',
    pruebas: [{ documento_id: 3, documento: 'diseño_red.pdf', paginas: [3], texto: 'VLAN 10: gestión' }],
  },
}
const RUTAS: Validacion = {
  id: 2, proyecto_id: 7, nombre: 'Tabla de rutas', tipo: 'patron', criterio: 'tabla de rutas', orden: 2,
  resultado: {
    estado: 'falla', explicacion: 'No aparece en ningún documento del proyecto', resumen: null,
    ejecutada: '2026-11-27T12:00:00+00:00', pruebas: [],
  },
}
const IA: Validacion = { id: 3, proyecto_id: 7, nombre: 'Direccionamiento', tipo: 'ia', criterio: '¿Está el plan de IPs?', orden: 3, resultado: null }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listValidations).mockResolvedValue([VLAN, RUTAS])
})

const fila = async (nombre: string) => (await screen.findByText(nombre)).closest('tr') as HTMLElement

describe('Validaciones', () => {
  it('pinta cada validación con su estado, explicación y prueba, y el resumen', async () => {
    render(<Validaciones proyectoId={7} />)
    const vlan = within(await fila('Aparecen las VLAN'))
    expect(vlan.getByLabelText('Cumple')).toBeInTheDocument()
    expect(vlan.getByText('Patrón')).toBeInTheDocument()
    expect(vlan.getByText('\\mVLAN\\s*\\d+')).toBeInTheDocument()
    expect(vlan.getByText('Aparece en 2 trozos de 1 documento')).toBeInTheDocument()
    expect(vlan.getByText('diseño_red.pdf · pág. 3')).toBeInTheDocument()
    expect(vlan.getByText('VLAN 10: gestión')).toBeInTheDocument()
    expect(within(await fila('Tabla de rutas')).getByLabelText('No cumple')).toBeInTheDocument()
    expect(screen.getByText('1 de 2 cumplen')).toBeInTheDocument()
    expect(listValidations).toHaveBeenCalledWith(7)
  })

  it('sin validaciones lo dice y no deja validar', async () => {
    vi.mocked(listValidations).mockResolvedValue([])
    render(<Validaciones proyectoId={7} />)
    expect(await screen.findByText('Este proyecto todavía no tiene validaciones.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Validar todo' })).toBeDisabled()
  })

  it('una sin ejecutar sale como «Sin validar» y no cuenta en el resumen', async () => {
    vi.mocked(listValidations).mockResolvedValue([VLAN, IA])
    render(<Validaciones proyectoId={7} />)
    expect(within(await fila('Direccionamiento')).getByLabelText('Sin validar')).toBeInTheDocument()
    expect(within(await fila('Direccionamiento')).getByText('Pregunta a la IA')).toBeInTheDocument()
    expect(screen.getByText('1 de 2 cumplen · 1 sin validar')).toBeInTheDocument()
  })

  it('añade una validación de patrón', async () => {
    vi.mocked(listValidations).mockResolvedValue([])
    vi.mocked(createValidation).mockResolvedValue({ ...RUTAS, resultado: null })
    render(<Validaciones proyectoId={7} />)
    const form = await screen.findByRole('form', { name: 'Nueva validación' })
    expect(within(form).getByRole('button', { name: 'Añadir' })).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Nombre'), 'Tabla de rutas')
    await userEvent.type(within(form).getByLabelText('Patrón'), 'tabla de rutas')
    await userEvent.click(within(form).getByRole('button', { name: 'Añadir' }))
    expect(createValidation).toHaveBeenCalledWith(7, { nombre: 'Tabla de rutas', tipo: 'patron', criterio: 'tabla de rutas' })
    expect(await fila('Tabla de rutas')).toBeInTheDocument()
    expect(within(form).getByLabelText('Nombre')).toHaveValue('')
  })

  it('con tipo IA el campo pasa a ser una pregunta', async () => {
    vi.mocked(createValidation).mockResolvedValue(IA)
    render(<Validaciones proyectoId={7} />)
    const form = await screen.findByRole('form', { name: 'Nueva validación' })
    await userEvent.selectOptions(within(form).getByLabelText('Tipo'), 'Pregunta a la IA')
    await userEvent.type(within(form).getByLabelText('Nombre'), 'Direccionamiento')
    await userEvent.type(within(form).getByLabelText('Pregunta'), '¿Está el plan de IPs?')
    await userEvent.click(within(form).getByRole('button', { name: 'Añadir' }))
    expect(createValidation).toHaveBeenCalledWith(7, { nombre: 'Direccionamiento', tipo: 'ia', criterio: '¿Está el plan de IPs?' })
  })

  it('muestra el error de la API si el patrón no vale', async () => {
    vi.mocked(createValidation).mockRejectedValue(
      new ApiError(422, 'El patrón no es una expresión regular válida: parentheses () not balanced'))
    render(<Validaciones proyectoId={7} />)
    const form = await screen.findByRole('form', { name: 'Nueva validación' })
    await userEvent.type(within(form).getByLabelText('Nombre'), 'Roto')
    await userEvent.type(within(form).getByLabelText('Patrón'), 'VLAN (')
    await userEvent.click(within(form).getByRole('button', { name: 'Añadir' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('parentheses () not balanced')
  })

  it('valida una sola y actualiza su fila', async () => {
    vi.mocked(runValidation).mockResolvedValue({ ...RUTAS, resultado: { ...VLAN.resultado!, explicacion: 'Aparece en 1 trozo de 1 documento' } })
    render(<Validaciones proyectoId={7} />)
    await userEvent.click(within(await fila('Tabla de rutas')).getByRole('button', { name: 'Validar' }))
    expect(runValidation).toHaveBeenCalledWith(2)
    expect(within(await fila('Tabla de rutas')).getByLabelText('Cumple')).toBeInTheDocument()
    expect(screen.getByText('2 de 2 cumplen')).toBeInTheDocument()
  })

  it('«Validar todo» va de una en una y sigue aunque una falle', async () => {
    vi.mocked(listValidations).mockResolvedValue([VLAN, IA, RUTAS])
    let soltar: (v: Validacion) => void = () => {}
    vi.mocked(runValidation)
      .mockImplementationOnce(() => new Promise((ok) => { soltar = ok }))
      .mockRejectedValueOnce(new ApiError(501, 'Las validaciones con IA todavía no se pueden ejecutar'))
      .mockResolvedValueOnce({ ...RUTAS, resultado: { ...RUTAS.resultado!, explicacion: 'Sigue sin aparecer' } })
    render(<Validaciones proyectoId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Validar todo' }))
    expect(screen.getByRole('status')).toHaveTextContent('Validando 1 de 3…')
    expect(runValidation).toHaveBeenCalledTimes(1)  // la siguiente no empieza hasta que acabe esta
    soltar(VLAN)
    expect(await within(await fila('Direccionamiento')).findByText('Las validaciones con IA todavía no se pueden ejecutar')).toBeInTheDocument()
    expect(within(await fila('Direccionamiento')).getByLabelText('Error')).toBeInTheDocument()
    expect(await screen.findByText('Sigue sin aparecer')).toBeInTheDocument()
    expect(runValidation).toHaveBeenNthCalledWith(3, 2)
    expect(screen.queryByText(/Validando/)).not.toBeInTheDocument()
  })

  it('edita una validación', async () => {
    vi.mocked(updateValidation).mockResolvedValue({ ...RUTAS, criterio: '\\mrutas?\\M', resultado: null })
    render(<Validaciones proyectoId={7} />)
    await userEvent.click(within(await fila('Tabla de rutas')).getByRole('button', { name: 'Editar' }))
    const form = screen.getByRole('form', { name: 'Editar validación' })
    expect(within(form).getByLabelText('Patrón')).toHaveValue('tabla de rutas')
    await userEvent.clear(within(form).getByLabelText('Patrón'))
    await userEvent.type(within(form).getByLabelText('Patrón'), '\\mrutas?\\M')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    expect(updateValidation).toHaveBeenCalledWith(2, { nombre: 'Tabla de rutas', tipo: 'patron', criterio: '\\mrutas?\\M' })
    expect(within(await fila('Tabla de rutas')).getByLabelText('Sin validar')).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Nueva validación' })).toBeInTheDocument()
  })

  it('borra con confirmación', async () => {
    vi.mocked(deleteValidation).mockResolvedValue()
    render(<Validaciones proyectoId={7} />)
    await userEvent.click(within(await fila('Tabla de rutas')).getByRole('button', { name: 'Borrar' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Borrar' }))
    expect(deleteValidation).toHaveBeenCalledWith(2)
    expect(screen.queryByText('Tabla de rutas')).not.toBeInTheDocument()
  })

  it('el desplegable enseña todos los documentos donde aparece y el resumen de la IA', async () => {
    const conResumen: Validacion = {
      ...IA,
      resultado: {
        estado: 'ok', explicacion: 'Se define el plan de IPs.', ejecutada: '2026-11-27T12:00:00+00:00',
        resumen: 'El direccionamiento está en el diseño de red (pág. 5) y en el anexo.',
        pruebas: [
          { documento_id: 3, documento: 'diseño_red.pdf', paginas: [5], texto: '10.0.0.0/24 gestión' },
          { documento_id: 4, documento: 'anexo.docx', paginas: [], texto: '10.0.1.0/24 usuarios' },
        ],
      },
    }
    vi.mocked(listValidations).mockResolvedValue([conResumen])
    render(<Validaciones proyectoId={7} />)
    const f = within(await fila('Direccionamiento'))
    expect(f.getByText('Visto en 2 documentos')).toBeInTheDocument()
    expect(f.getByText('El direccionamiento está en el diseño de red (pág. 5) y en el anexo.')).toBeInTheDocument()
    expect(f.getByText('diseño_red.pdf · pág. 5')).toBeInTheDocument()
    expect(f.getByText('anexo.docx')).toBeInTheDocument()
    expect(f.getByText('10.0.1.0/24 usuarios')).toBeInTheDocument()
  })

  it('varios trozos del mismo documento se resumen como «documento · N trozos»', async () => {
    const dos = { ...VLAN.resultado!, pruebas: [VLAN.resultado!.pruebas[0], { ...VLAN.resultado!.pruebas[0], paginas: [4] }] }
    vi.mocked(listValidations).mockResolvedValue([{ ...VLAN, resultado: dos }])
    render(<Validaciones proyectoId={7} />)
    expect(within(await fila('Aparecen las VLAN')).getByText('diseño_red.pdf · 2 trozos')).toBeInTheDocument()
  })
})
