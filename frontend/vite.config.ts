/// <reference types="vitest/config" />
/**
 * Configuración de Vite (compilar y servir en desarrollo) y de Vitest (tests).
 *
 * Para qué:
 *   - `npm run build` compila la app a dist/, que el Dockerfile copia a la imagen web.
 *   - `npm run dev` levanta un servidor de desarrollo en localhost:5173 con recarga en caliente.
 *     Su proxy reenvía /api a localhost:8000, así que para probar el login en modo desarrollo hay
 *     que arrancar la API aparte (`uvicorn app.main:app --port 8000` en api/). La app de Docker
 *     está en http://localhost.
 *   - `npm test` ejecuta los tests en jsdom (un navegador simulado) con src/setupTests.ts.
 */

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  test: { environment: 'jsdom', setupFiles: ['./src/setupTests.ts'] },
})
