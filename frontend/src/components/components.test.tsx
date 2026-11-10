/**
 * Tests de los componentes ConfirmDialog y DropZone.
 *
 * Para qué: comprobar el aviso de confirmación (qué se ve, qué callback llama cada botón y
 * Escape) y la zona de arrastrar archivos (soltar, elegir con el selector y desactivada).
 *
 * jsdom no implementa showModal()/close() del <dialog>: se simulan con el atributo `open`.
 */

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import ConfirmDialog from './ConfirmDialog'
import DropZone from './DropZone'

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})

const dialogo = (open: boolean) => {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  render(
    <ConfirmDialog open={open} titulo="Borrar proyecto" mensaje="Se borrarán sus documentos" confirmar="Borrar"
      onConfirm={onConfirm} onCancel={onCancel} />,
  )
  return { onConfirm, onCancel }
}

describe('ConfirmDialog', () => {
  it('abierto muestra título y mensaje', () => {
    dialogo(true)
    expect(screen.getByRole('dialog', { name: 'Borrar proyecto' })).toBeInTheDocument()
    expect(screen.getByText('Se borrarán sus documentos')).toBeInTheDocument()
  })

  it('«Borrar» llama a onConfirm', async () => {
    const { onConfirm, onCancel } = dialogo(true)
    await userEvent.click(screen.getByRole('button', { name: 'Borrar' }))
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('«Cancelar» llama a onCancel y no a onConfirm', async () => {
    const { onConfirm, onCancel } = dialogo(true)
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(onCancel).toHaveBeenCalledOnce()
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('Escape (evento cancel del dialog) llama a onCancel', () => {
    const { onCancel } = dialogo(true)
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('cerrado no se ve', () => {
    dialogo(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Borrar' })).not.toBeInTheDocument()
  })
})

describe('DropZone', () => {
  const a = new File(['a'], 'a.txt')
  const b = new File(['b'], 'b.txt')

  it('soltar archivos llama a onFiles con ellos', () => {
    const onFiles = vi.fn()
    render(<DropZone onFiles={onFiles} />)
    fireEvent.drop(screen.getByText(/Arrastra aquí los archivos/), { dataTransfer: { files: [a, b] } })
    expect(onFiles).toHaveBeenCalledWith([a, b])
  })

  it('elegir con el selector llama a onFiles', async () => {
    const onFiles = vi.fn()
    render(<DropZone onFiles={onFiles} />)
    const input = screen.getByLabelText('Elegir archivos')
    expect(input).toHaveAttribute('multiple')
    await userEvent.upload(input, [a, b])
    expect(onFiles).toHaveBeenCalledWith([a, b])
  })

  it('desactivada no llama a onFiles al soltar ni deja pulsar', () => {
    const onFiles = vi.fn()
    render(<DropZone onFiles={onFiles} disabled />)
    fireEvent.drop(screen.getByText(/Arrastra aquí los archivos/), { dataTransfer: { files: [a] } })
    expect(onFiles).not.toHaveBeenCalled()
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
