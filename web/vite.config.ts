import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8765',
    },
  },
  build: {
    // Empaquetado con el paquete Python: penfold sirve estos archivos en start.
    outDir: '../src/penfold/static',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
    restoreMocks: true,
  },
});
