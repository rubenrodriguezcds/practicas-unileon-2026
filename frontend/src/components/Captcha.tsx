/**
 * Captcha anti-bot (ALTCHA): la casilla «No soy un robot» del login y del reseteo.
 *
 * Para qué: al marcarla, el navegador pide un reto a la API (GET /api/captcha), resuelve un
 * pequeño cálculo (~1 s) y entrega el resultado («payload») por `onChange`. La pantalla lo envía
 * junto con el formulario y la API lo comprueba.
 *
 * Por qué ALTCHA: open source y servido por nosotros, sin cuentas de Google ni de Cloudflare,
 * sin rastreo ni aviso de cookies.
 *
 * Quién lo usa: pages/Login.tsx y pages/ResetPassword.tsx.
 *
 * Notas:
 *   - Cada reto vale una sola vez. Tras un intento fallido la pantalla cambia la `key` de este
 *     componente: React lo vuelve a montar y el widget pide un reto nuevo.
 *   - `altcha-widget` es un web component (no es React), por eso el evento se escucha a mano.
 */

import { useEffect, useRef } from 'react'
import 'altcha'
import 'altcha/i18n/es-es'

declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'altcha-widget': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & { challenge?: string; language?: string; name?: string }
    }
  }
}

/**
 * @param props.onChange recibe el payload al resolverse, o `null` si deja de valer (caduca, error).
 */
export default function Captcha({ onChange }: { onChange: (payload: string | null) => void }) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const widget = ref.current
    if (!widget) return
    const listener = (e: Event) => {
      const { state, payload } = (e as CustomEvent<{ state: string; payload?: string }>).detail
      onChange(state === 'verified' && payload ? payload : null)
    }
    widget.addEventListener('statechange', listener)
    return () => widget.removeEventListener('statechange', listener)
  }, [onChange])

  return <altcha-widget ref={ref} challenge="/api/captcha" language="es-es" name="altcha" />
}
