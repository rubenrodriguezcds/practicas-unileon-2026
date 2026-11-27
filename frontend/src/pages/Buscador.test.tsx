/**
 * Tests de la página «Buscador» (asistente IA, fase 1: buscador de prueba).
 *
 * Para qué: comprobar lo que ve el administrador: cada trozo con su documento (enlace a la ficha del
 * proyecto), sección, páginas, texto y las tres puntuaciones con 3 decimales; que el filtro de
 * proyecto se envía; el aviso sin resultados; y que los errores de la API (503 sin Ollama…) se
 * muestran tal cual.
 *
 * El cliente de API se simula (vi.mock), así que no hace falta backend.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError, listProjects, searchFragments, summarizeSearch, type Proyecto, type ResultadoBusqueda,
} from '../api/client'
import Buscador from './Buscador'

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  listProjects: vi.fn(),
  searchFragments: vi.fn(),
  summarizeSearch: vi.fn(),
}))

// jsdom no implementa el desplazamiento; las citas del resumen lo usan para ir a su resultado.
Element.prototype.scrollIntoView = vi.fn()

const ALFA: Proyecto = { id: 3, nombre: 'Proyecto Alfa', tipo: null, descripcion: null, num_documentos: 2 }
const BETA: Proyecto = { id: 4, nombre: 'Beta', tipo: null, descripcion: null, num_documentos: 0 }
const RESUMEN: ResultadoBusqueda = {
  documento_id: 8, documento: 'informe.pdf', proyecto_id: 3, proyecto: 'Proyecto Alfa',
  titulos: ['Proyecto Ficticio Alfa', '1. Resumen'], paginas: [1, 2],
  texto: '1. Resumen\nLa migración costará 48.500 €.',
  puntuacion_vector: 0.60274, puntuacion_texto: null, puntuacion: 0.016393,
}
const DOCX: ResultadoBusqueda = { ...RESUMEN, documento_id: 5, documento: 'memoria.docx', titulos: [], paginas: [],
  texto: 'Riesgos', puntuacion_vector: 0.5, puntuacion_texto: 0.18, puntuacion: 0.0328 }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listProjects).mockResolvedValue([ALFA, BETA])
  vi.mocked(searchFragments).mockResolvedValue([RESUMEN, DOCX])
  vi.mocked(summarizeSearch).mockResolvedValue({ resumen: 'La migración costará 48.500 € [1] y tiene riesgos [1, 2].', fuentes: 2, encontrado: true })
})

const pintar = () => render(<MemoryRouter><Buscador /></MemoryRouter>)

async function buscar(pregunta: string) {
  await userEvent.type(screen.getByLabelText('Pregunta'), pregunta)
  await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
}

describe('Buscador', () => {
  it('pinta cada trozo con su documento, sección, páginas, texto y puntuaciones', async () => {
    pintar()
    await buscar('¿cuánto cuesta la migración?')
    const resultados = await screen.findAllByRole('article')
    expect(resultados).toHaveLength(2)
    const primero = within(resultados[0])
    expect(primero.getByRole('link', { name: 'informe.pdf' })).toHaveAttribute('href', '/proyectos/3')
    expect(primero.getByText(/Proyecto Alfa/)).toBeInTheDocument()
    expect(primero.getByText('Proyecto Ficticio Alfa › 1. Resumen')).toBeInTheDocument()
    expect(primero.getByText('págs. 1, 2')).toBeInTheDocument()
    expect(primero.getByText(/La migración costará 48\.500 €\./)).toBeInTheDocument()
    expect(primero.getByText('Significado 0,603 · Palabras — · Combinada 0,016')).toBeInTheDocument()
    expect(within(resultados[1]).getByText('Significado 0,500 · Palabras 0,180 · Combinada 0,033')).toBeInTheDocument()
  })

  it('busca en todos los proyectos o solo en el elegido', async () => {
    pintar()
    await screen.findByRole('option', { name: 'Proyecto Alfa' })
    await buscar('riesgos')
    expect(searchFragments).toHaveBeenLastCalledWith('riesgos', null)
    await userEvent.selectOptions(screen.getByLabelText('Proyecto'), 'Proyecto Alfa')
    await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(searchFragments).toHaveBeenLastCalledWith('riesgos', 3)
  })

  it('no deja buscar con la pregunta vacía', async () => {
    pintar()
    expect(screen.getByRole('button', { name: 'Buscar' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Pregunta'), '   ')
    expect(screen.getByRole('button', { name: 'Buscar' })).toBeDisabled()
  })

  it('sin resultados lo dice', async () => {
    vi.mocked(searchFragments).mockResolvedValue([])
    pintar()
    await buscar('receta de tortilla')
    expect(await screen.findByText('No hay trozos que se parezcan')).toBeInTheDocument()
  })

  it('muestra el error de la API tal cual (503 sin Ollama)', async () => {
    vi.mocked(searchFragments).mockRejectedValue(
      new ApiError(503, 'El buscador no está disponible: Ollama no responde en http://x (ConnectError)'))
    pintar()
    await buscar('migración')
    expect(await screen.findByRole('alert')).toHaveTextContent('El buscador no está disponible: Ollama no responde')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('una búsqueda nueva quita los resultados y el error anteriores', async () => {
    vi.mocked(searchFragments).mockRejectedValueOnce(new ApiError(503, 'Sin Ollama'))
    pintar()
    await buscar('migración')
    expect(await screen.findByRole('alert')).toHaveTextContent('Sin Ollama')
    await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(await screen.findAllByRole('article')).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  describe('resumen con IA', () => {
    it('sale encima de los resultados, citando, con la misma pregunta y proyecto', async () => {
      pintar()
      await buscar('¿cuánto cuesta la migración?')
      const bloque = await screen.findByRole('region', { name: 'Resumen con IA' })
      expect(await within(bloque).findByText(/La migración costará 48.500 €/)).toBeInTheDocument()
      expect(within(bloque).getByText(/Generado con IA/)).toBeInTheDocument()
      expect(summarizeSearch).toHaveBeenCalledWith('¿cuánto cuesta la migración?', null)
      // [1] y [1, 2] se convierten en enlaces a sus resultados.
      expect(within(bloque).getAllByRole('button', { name: 'Ir a la fuente 1' })).toHaveLength(2)
      expect(within(bloque).getByRole('button', { name: 'Ir a la fuente 2' })).toBeInTheDocument()
    })

    it('mientras se genera lo dice, y los resultados ya se ven', async () => {
      vi.mocked(summarizeSearch).mockReturnValue(new Promise(() => {}))
      pintar()
      await buscar('migración')
      expect(await screen.findAllByRole('article')).toHaveLength(2)
      expect(screen.getByText('Generando resumen…')).toBeInTheDocument()
    })

    it('pulsar una cita lleva a su resultado y lo resalta', async () => {
      pintar()
      await buscar('migración')
      const bloque = await screen.findByRole('region', { name: 'Resumen con IA' })
      await userEvent.click(await within(bloque).findByRole('button', { name: 'Ir a la fuente 2' }))
      const segundo = (await screen.findAllByRole('article'))[1]
      expect(segundo.scrollIntoView).toHaveBeenCalled()
      expect(segundo).toHaveClass('resaltado')
    })

    it('con la respuesta encontrada, los resultados se ven abiertos', async () => {
      pintar()
      await buscar('migración')
      await screen.findByRole('button', { name: 'Ir a la fuente 2' })
      expect(screen.queryByText(/resultados poco relevantes/)).not.toBeInTheDocument()
    })

    it('si no lo encuentra, los resultados quedan plegados como poco relevantes', async () => {
      vi.mocked(summarizeSearch).mockResolvedValue({ resumen: 'No lo encuentro en los documentos.', fuentes: 2, encontrado: false })
      pintar()
      await buscar('¿quién ganó el mundial?')
      const resumen = screen.getByRole('region', { name: 'Resumen con IA' })
      expect(await within(resumen).findByText('No lo encuentro en los documentos.')).toBeInTheDocument()
      const plegado = screen.getByText('Ver 2 resultados poco relevantes').closest('details') as HTMLElement
      expect(plegado).not.toHaveAttribute('open')
      expect(within(plegado).getAllByRole('article', { hidden: true })).toHaveLength(2)
    })

    it('si falla, enseña el motivo y los resultados siguen', async () => {
      vi.mocked(summarizeSearch).mockRejectedValue(new ApiError(503, 'El resumen no está disponible: Ollama no responde'))
      pintar()
      await buscar('migración')
      const bloque = await screen.findByRole('region', { name: 'Resumen con IA' })
      expect(await within(bloque).findByText('El resumen no está disponible: Ollama no responde')).toBeInTheDocument()
      expect(screen.getAllByRole('article')).toHaveLength(2)
    })

    it('sin resultados, o si falla la búsqueda, ni se pide', async () => {
      vi.mocked(searchFragments).mockResolvedValueOnce([])
      pintar()
      await buscar('tortilla')
      await screen.findByText('No hay trozos que se parezcan')
      vi.mocked(searchFragments).mockRejectedValueOnce(new ApiError(503, 'Sin Ollama'))
      await userEvent.click(screen.getByRole('button', { name: 'Buscar' }))
      await screen.findByRole('alert')
      expect(summarizeSearch).not.toHaveBeenCalled()
      expect(screen.queryByRole('region', { name: 'Resumen con IA' })).not.toBeInTheDocument()
    })
  })
})
