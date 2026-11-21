import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import { scanUpload } from './scan-upload.ts'

const PORT = 5173
const repoRoot = fileURLToPath(new URL('..', import.meta.url))

// The app reads the team's real run files (contracts/, data/, assets/) straight from the repo root.
export default defineConfig({
  plugins: [react(), tailwindcss(), scanUpload(repoRoot, PORT)],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@repo': repoRoot,
    },
  },
  server: {
    port: PORT,
    strictPort: true,
    // Listen on the local network too, so a phone on the same Wi-Fi can open the upload page from the QR code.
    host: true,
    fs: { allow: ['..'] },
    // The agent server (server/app.py). Point API_TARGET at a teammate's machine to use theirs.
    proxy: {
      '/api': { target: process.env.API_TARGET ?? 'http://localhost:8000', changeOrigin: true },
      // IKEA product photos, same-origin, so the 3D room can read their pixels (rug textures, lamp cut-outs).
      '/ikea-img': { target: 'https://www.ikea.com', changeOrigin: true, rewrite: (p) => p.replace(/^\/ikea-img/, '') },
    },
  },
})
