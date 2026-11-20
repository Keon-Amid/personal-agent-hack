import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // The harness imports ../data/products.json and ../contracts/plan.*.json from the repo root.
  server: { port: 5173, fs: { allow: ['..'] } },
})
