import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 서버에서 /api 요청은 FastAPI(8000)로 프록시한다
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
