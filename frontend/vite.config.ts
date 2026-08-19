/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    proxy: {
      '/api': { target: 'http://localhost:8502', changeOrigin: true },
      '/health': { target: 'http://localhost:8502', changeOrigin: true },
      '/modules': { target: 'http://localhost:8502', changeOrigin: true },
      '/cache': { target: 'http://localhost:8502', changeOrigin: true },
      '/backup': { target: 'http://localhost:8502', changeOrigin: true },
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
  },
})
