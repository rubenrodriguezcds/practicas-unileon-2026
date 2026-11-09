/**
 * Pantalla principal para el usuario que ha iniciado sesión.
 *
 * Para qué: saluda al usuario. Es el punto de partida donde irán las funciones del gestor
 * documental. El menú y «Cerrar sesión» están en components/Layout.tsx, común a todas las
 * pantallas con sesión.
 *
 * Quién lo usa: App.tsx, en la ruta /, solo si hay sesión (dentro de Layout).
 */

/**
 * Saludo de la pantalla de inicio.
 * @param props.username nombre a mostrar en el saludo.
 */
export default function Home({ username }: { username: string }) {
  return (
    <main className="card">
      <h1>Hola, {username}</h1>
    </main>
  )
}
