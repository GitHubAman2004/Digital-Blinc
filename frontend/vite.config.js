import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        // NOTE FOR REAL INTEGRATION:
        // If your Flask backend runs on a different PC or different IP/port,
        // change target below to point to your backend IP:
        // e.g., target: 'http://192.168.1.50:5000'
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
        secure: false
      }
    }
  }
})
