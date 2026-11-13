/**
 * Aviso modal de confirmación («¿Seguro que quieres borrar…?»).
 *
 * Para qué: pedir confirmación antes de una acción que no se puede deshacer (borrar un proyecto
 * o un documento) con un diálogo accesible: foco atrapado y Escape para cancelar.
 *
 * Por qué existe: el <dialog> nativo ya da todo eso; este componente solo lo conecta a React y se
 * reutiliza en todas las pantallas en lugar de repetir el aviso.
 *
 * Quién lo usa: las pantallas de proyectos.
 *
 * Notas: `open` es la única fuente de verdad; Escape no cierra por su cuenta, avisa a `onCancel`
 * y es el padre quien pone `open` a false.
 */

import { useEffect, useRef } from 'react'

/**
 * @param props.open si el aviso está visible.
 * @param props.titulo título (nombra el diálogo para los lectores de pantalla).
 * @param props.mensaje explicación de lo que va a pasar.
 * @param props.confirmar texto del botón de confirmar (p. ej. «Borrar»).
 * @param props.onConfirm se llama al confirmar.
 * @param props.onCancel se llama al pulsar «Cancelar» o Escape.
 */
export default function ConfirmDialog({ open, titulo, mensaje, confirmar, onConfirm, onCancel }: {
  open: boolean
  titulo: string
  mensaje: string
  confirmar: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-titulo"
      onCancel={(e) => { e.preventDefault(); onCancel() }}
    >
      <h2 id="confirm-titulo">{titulo}</h2>
      <p>{mensaje}</p>
      <div className="botones">
        <button className="secundario" onClick={onCancel}>Cancelar</button>
        <button className="peligro" onClick={onConfirm}>{confirmar}</button>
      </div>
    </dialog>
  )
}
