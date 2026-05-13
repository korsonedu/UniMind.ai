import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
    },
  },
  resolve: {
    alias: {
      // @ → parent src for shared modules (api, stores, components)
      "@": path.resolve(__dirname, "../src"),
    },
  },
})
