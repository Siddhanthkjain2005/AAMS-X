import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('commonjsHelpers') || id.includes('/node_modules/@babel/runtime/') || id.includes('/node_modules/use-sync-external-store/')) return 'react'
          if (/node_modules\/(react|react-dom|react-is|scheduler)\//.test(id)) return 'react'
          if (id.includes('/node_modules/zustand/')) return 'state'
          if (/node_modules\/(recharts|d3-[^/]+)\//.test(id)) return 'charts'
          if (/node_modules\/(three|@react-three|three-stdlib)\//.test(id)) return 'three'
        },
      },
    },
  },
})
