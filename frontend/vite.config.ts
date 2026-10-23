/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // Vite incorpora i file piccoli (come certi font) nel CSS come `data:`: la nostra
    // Content-Security-Policy (`font-src 'self'`) li blocca. Restano file veri, serviti da qui.
    assetsInlineLimit: 0,
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': { target: 'http://127.0.0.1:8502', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8502', changeOrigin: true },
      '/modules': { target: 'http://127.0.0.1:8502', changeOrigin: true },
      '/cache': { target: 'http://127.0.0.1:8502', changeOrigin: true },
      '/backup': { target: 'http://127.0.0.1:8502', changeOrigin: true },
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    // e2e/ holds Playwright specs, which need a real browser and a running
    // backend. Vitest cannot execute them and fails at collection; they are
    // run separately with `npm run e2e`.
    exclude: ['node_modules/**', 'dist/**', 'e2e/**'],
  },
})
