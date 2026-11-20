import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// The app reads the team's real run files (contracts/, data/, assets/) straight from the repo root.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@repo': fileURLToPath(new URL('..', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: ['..'] },
    // The agent server (server/app.py). Point API_TARGET at a teammate's machine to use theirs.
    proxy: { '/api': { target: process.env.API_TARGET ?? 'http://localhost:8000', changeOrigin: true } },
  },
})
