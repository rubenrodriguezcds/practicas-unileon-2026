/**
 * Zona para arrastrar archivos o elegirlos con el selector del sistema.
 *
 * Para qué: subir documentos a un proyecto, con el ratón (arrastrar y soltar) o con el teclado
 * (el botón abre el selector).
 *
 * Por qué existe: separar la entrada de archivos de la pantalla; esta solo recibe `File[]`.
 *
 * Quién lo usa: la pantalla de detalle de un proyecto.
 *
 * Notas: solo `onDrop` y el selector llaman a `onFiles`; arrastrar encima solo resalta la zona.
 * Con `disabled` (p. ej. mientras se sube) ni se resalta ni se acepta nada.
 */

import { useRef, useState, type DragEvent } from 'react'

/**
 * @param props.onFiles recibe los archivos soltados o elegidos.
 * @param props.disabled desactiva la zona y el botón.
 */
export default function DropZone({ onFiles, disabled = false }: { onFiles: (files: File[]) => void; disabled?: boolean }) {
  const [encima, setEncima] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  function soltar(e: DragEvent) {
    e.preventDefault()
    setEncima(false)
    if (disabled) return
    const files = Array.from(e.dataTransfer.files)
    if (files.length) onFiles(files)
  }

  return (
    <div
      className={encima ? 'dropzone encima' : 'dropzone'}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setEncima(true) }}
      onDragLeave={() => setEncima(false)}
      onDrop={soltar}
    >
      <p>Arrastra aquí los archivos o pulsa para elegirlos</p>
      <button type="button" className="secundario" disabled={disabled} onClick={() => input.current?.click()}>
        Elegir archivos
      </button>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        aria-label="Elegir archivos"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = '' // permite volver a elegir el mismo archivo
          if (files.length) onFiles(files)
        }}
      />
    </div>
  )
}
