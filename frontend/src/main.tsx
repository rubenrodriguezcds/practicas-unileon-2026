/**
 * Punto de entrada del frontend: lo primero que ejecuta el navegador.
 *
 * Para qué: monta el componente <App /> dentro del <div id="root"> de index.html y carga los
 * estilos globales.
 *
 * Por qué BrowserRouter aquí: activa las rutas del navegador (/login, /) para toda la app.
 * StrictMode solo afecta en desarrollo (avisa de malas prácticas; ejecuta algunos efectos dos veces).
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
