/**
 * Logo de la empresa, fijo arriba a la izquierda.
 *
 * Para qué: identidad visual en las pantallas públicas (sin sesión).
 *
 * Quién lo usa: solo pages/Login.tsx y pages/ResetPassword.tsx. A propósito no va en un layout
 * común: el layout y el menú de la parte con sesión los tocan otras issues.
 *
 * Notas: la imagen está en public/, así que Vite la sirve tal cual en /cds-logo.png.
 */

export default function Logo() {
  return (
    <header className="brand">
      <img src="/cds-logo.png" alt="CDS" />
    </header>
  )
}
