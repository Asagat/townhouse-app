import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Конфиг dev-сервера настраивается через env (префикс VITE_):
//   VITE_DEV_HOST  — разрешённый host + hmr.host (по умолчанию townhouse.sagacloud.kz для VPS)
//   VITE_DEV_PORT  — порт (по умолчанию 5173)
// Локально задайте VITE_DEV_HOST=localhost (см. .env.example).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devHost = env.VITE_DEV_HOST || 'townhouse.sagacloud.kz'
  const devPort = Number(env.VITE_DEV_PORT) || 5173
  return {
    plugins: [react()],
    server: {
      host: true,
      port: devPort,
      allowedHosts: [devHost],
      hmr: {
        host: devHost,
        protocol: 'ws'
      }
    }
  }
})
