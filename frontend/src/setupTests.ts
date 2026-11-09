/**
 * Preparación común de los tests del frontend (Vitest la carga antes de cada fichero).
 *
 * Para qué: añade los comprobadores de jest-dom (toBeInTheDocument, toBeDisabled…) y limpia el
 * DOM simulado después de cada test, para que un test no vea lo que pintó el anterior.
 * Está declarado en vite.config.ts (test.setupFiles).
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)
