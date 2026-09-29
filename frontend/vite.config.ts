import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the React app runs on :5173 and the Python API on :8000.
// Proxying means the browser only ever talks to one origin, so the app code
// can use plain paths like /tracks and work unchanged in production, where
// the backend serves the built files itself.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/tracks': 'http://127.0.0.1:8000',
      '/stems': 'http://127.0.0.1:8000',
      '/jobs': 'http://127.0.0.1:8000',
    },
  },
})
