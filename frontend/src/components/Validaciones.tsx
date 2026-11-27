/**
 * Sección «Validación» de la ficha del proyecto: qué tiene que aparecer en sus documentos y si aparece.
 *
 * Para qué: el director de proyectos define validaciones («aparecen las VLAN», «está la tabla de
 * rutas»…) y ve de un vistazo cuáles se cumplen (✅), cuáles no (❌) y cuáles fallaron al
 * comprobarse (⚠️), con la explicación y, al desplegar, todos los documentos donde aparece (las
 * pruebas) y, en las de IA, un resumen corto. Así puede
 * rechazar un proyecto con la documentación incompleta. Diseño en
 * docs/superpowers/specs/2026-11-27-validaciones-design.md.
 *
 * Quién lo usa: pages/ProyectoDetalle.tsx, debajo de los documentos.
 *
 * Notas:
 *  - «Validar todo» las ejecuta DE UNA EN UNA (una petición cada una): las de IA tardan ~1 min y
 *    una sola petición para todas se cortaría. Si una falla (p. ej. Ollama caído), lo muestra en
 *    su fila y sigue con la siguiente.
 *  - El mismo formulario sirve para añadir y para editar; editar borra el resultado (lo hace la API).
 */

import { useEffect, useState, type SubmitEvent } from 'react'
import {
  createValidation, deleteValidation, listValidations, runValidation, updateValidation,
  type ResultadoValidacion, type Validacion, type ValidacionIn,
} from '../api/client'
import ConfirmDialog from './ConfirmDialog'

const mensaje = (err: unknown) => (err instanceof Error ? err.message : 'Error inesperado')

const TIPOS = { patron: 'Patrón', ia: 'Pregunta a la IA' } as const
const VACIA: ValidacionIn = { nombre: '', tipo: 'patron', criterio: '' }

/** Copia de `errores` sin el de la validación `id`. */
function sinError(errores: Record<number, string>, id: number) {
  const copia = { ...errores }
  delete copia[id]
  return copia
}

/** Icono del estado, con su texto para lectores de pantalla. */
function Estado({ v, error }: { v: Validacion; error?: string }) {
  const [icono, texto] = error ? ['⚠️', 'Error']
    : !v.resultado ? ['—', 'Sin validar']
    : { ok: ['✅', 'Cumple'], falla: ['❌', 'No cumple'], error: ['⚠️', 'Error'] }[v.resultado.estado]
  return <span role="img" aria-label={texto} title={texto}>{icono}</span>
}

/** «diseño_red.pdf · pág. 3» (Word no tiene páginas fijas: solo el nombre). */
function lugar(p: { documento: string; paginas: number[] }) {
  if (p.paginas.length === 0) return p.documento
  return `${p.documento} · ${p.paginas.length === 1 ? 'pág.' : 'págs.'} ${p.paginas.join(', ')}`
}

/** Desplegable con el resumen de la IA (si lo hay) y todos los documentos donde aparece. */
function Pruebas({ resultado }: { resultado: ResultadoValidacion }) {
  const { pruebas, resumen } = resultado
  const documentos = new Set(pruebas.map((p) => p.documento_id)).size
  return (
    <details>
      <summary>
        {pruebas.length === 1 ? lugar(pruebas[0])
          : documentos === 1 ? `${pruebas[0].documento} · ${pruebas.length} trozos`
          : `Visto en ${documentos} documentos`}
      </summary>
      {resumen && <p className="resumen-ia">{resumen}</p>}
      <ul className="pruebas">
        {pruebas.map((p, i) => (
          <li key={i}>
            {pruebas.length > 1 && <strong>{lugar(p)}</strong>}
            <p>{p.texto}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}

export default function Validaciones({ proyectoId }: { proyectoId: number }) {
  const [validaciones, setValidaciones] = useState<Validacion[] | null>(null)
  const [form, setForm] = useState<ValidacionIn>(VACIA)
  const [editando, setEditando] = useState<number | null>(null)
  const [borrando, setBorrando] = useState<Validacion | null>(null)
  const [errores, setErrores] = useState<Record<number, string>>({})  // fallo al ejecutar, por validación
  const [progreso, setProgreso] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    listValidations(proyectoId).then(setValidaciones).catch((err) => setError(mensaje(err)))
  }, [proyectoId])

  const reemplazar = (v: Validacion) => setValidaciones((vs) => (vs ?? []).map((x) => (x.id === v.id ? v : x)))

  /** Ejecuta una validación; si falla, guarda el motivo en su fila. */
  async function ejecutar(id: number) {
    setErrores((e) => sinError(e, id))
    try {
      reemplazar(await runValidation(id))
    } catch (err) {
      setErrores((e) => ({ ...e, [id]: mensaje(err) }))
    }
  }

  async function validarUna(id: number) {
    setBusy(true)
    await ejecutar(id)
    setBusy(false)
  }

  async function validarTodo() {
    const ids = (validaciones ?? []).map((v) => v.id)
    setBusy(true)
    for (const [i, id] of ids.entries()) {
      setProgreso(`Validando ${i + 1} de ${ids.length}…`)
      await ejecutar(id)
    }
    setProgreso('')
    setBusy(false)
  }

  async function guardar(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    setBusy(true)
    setError('')
    const datos = { ...form, nombre: form.nombre.trim(), criterio: form.criterio.trim() }
    try {
      if (editando === null) {
        const nueva = await createValidation(proyectoId, datos)
        setValidaciones((vs) => [...(vs ?? []), nueva])
      } else {
        reemplazar(await updateValidation(editando, datos))
        setErrores((e) => sinError(e, editando))
        setEditando(null)
      }
      setForm(VACIA)
    } catch (err) {
      setError(mensaje(err))
    } finally {
      setBusy(false)
    }
  }

  async function confirmarBorrado() {
    const v = borrando
    setBorrando(null)
    if (!v) return
    try {
      await deleteValidation(v.id)
      setValidaciones((vs) => (vs ?? []).filter((x) => x.id !== v.id))
    } catch (err) {
      setError(mensaje(err))
    }
  }

  function editar(v: Validacion) {
    setEditando(v.id)
    setForm({ nombre: v.nombre, tipo: v.tipo, criterio: v.criterio })
  }

  const lista = validaciones ?? []
  const validadas = lista.filter((v) => v.resultado)
  const cumplen = validadas.filter((v) => v.resultado?.estado === 'ok').length
  const sinValidar = lista.length - validadas.length

  return (
    <section className="validaciones" aria-labelledby="titulo-validacion">
      <h2 id="titulo-validacion">Validación</h2>
      <p className="hint">
        Lo que tiene que aparecer en los documentos del proyecto para darlo por completo. Los patrones no distinguen
        mayúsculas ni acentos; las preguntas las responde la IA citando el trozo.
      </p>

      {error && <p role="alert" className="error">{error}</p>}

      {validaciones === null ? (
        !error && <p className="hint">Cargando…</p>
      ) : (
        <>
          <div className="barra-acciones">
            {lista.length > 0 && (
              <p className="resumen">
                {validadas.length > 0 ? `${cumplen} de ${lista.length} cumplen` : 'Sin validar'}
                {validadas.length > 0 && sinValidar > 0 && ` · ${sinValidar} sin validar`}
              </p>
            )}
            {progreso && <span role="status" className="hint">{progreso}</span>}
            <button onClick={validarTodo} disabled={busy || lista.length === 0}>Validar todo</button>
          </div>

          {lista.length === 0 ? (
            <p className="hint">Este proyecto todavía no tiene validaciones.</p>
          ) : (
            <table>
              <thead>
                <tr><th><span className="oculto">Estado</span></th><th>Validación</th><th>Resultado</th><th><span className="oculto">Acciones</span></th></tr>
              </thead>
              <tbody>
                {lista.map((v) => (
                  <tr key={v.id}>
                    <td className="estado"><Estado v={v} error={errores[v.id]} /></td>
                    <td>
                      <strong>{v.nombre}</strong>
                      <br /><span className="hint">{TIPOS[v.tipo]}</span>: <code>{v.criterio}</code>
                    </td>
                    <td>
                      {errores[v.id] ? <span className="error">{errores[v.id]}</span> : v.resultado?.explicacion}
                      {!errores[v.id] && v.resultado && v.resultado.pruebas.length > 0 && (
                        <Pruebas resultado={v.resultado} />
                      )}
                    </td>
                    <td className="acciones">
                      <button className="secundario" disabled={busy} onClick={() => validarUna(v.id)}>Validar</button>
                      <button className="secundario" disabled={busy} onClick={() => editar(v)}>Editar</button>
                      <button className="peligro" disabled={busy} onClick={() => setBorrando(v)}>Borrar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <form className="fila" onSubmit={guardar} aria-label={editando === null ? 'Nueva validación' : 'Editar validación'}>
            <label>
              Nombre
              <input id="validacion-nombre" value={form.nombre} maxLength={200} autoComplete="off"
                onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
            </label>
            <label>
              Tipo
              <select id="validacion-tipo" value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as ValidacionIn['tipo'] })}>
                <option value="patron">{TIPOS.patron}</option>
                <option value="ia">{TIPOS.ia}</option>
              </select>
            </label>
            <label className="ancho">
              {form.tipo === 'patron' ? 'Patrón' : 'Pregunta'}
              <input id="validacion-criterio" value={form.criterio} maxLength={1000} autoComplete="off"
                placeholder={form.tipo === 'patron' ? 'p. ej. \\mVLAN\\s*\\d+' : 'p. ej. ¿Está definida la tabla de rutas?'}
                onChange={(e) => setForm({ ...form, criterio: e.target.value })} />
            </label>
            <button type="submit" disabled={busy || !form.nombre.trim() || !form.criterio.trim()}>
              {editando === null ? 'Añadir' : 'Guardar'}
            </button>
            {editando !== null && (
              <button type="button" className="secundario" onClick={() => { setEditando(null); setForm(VACIA) }}>Cancelar</button>
            )}
          </form>
        </>
      )}

      <ConfirmDialog
        open={borrando !== null}
        titulo={`¿Borrar la validación «${borrando?.nombre ?? ''}»?`}
        mensaje="Se borra también su último resultado."
        confirmar="Borrar"
        onConfirm={confirmarBorrado}
        onCancel={() => setBorrando(null)}
      />
    </section>
  )
}
