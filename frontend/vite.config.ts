import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Конфиг dev-сервера настраивается через env (префикс VITE_):
//   VITE_DEV_HOST  — разрешённый host + hmr.host (по умолчанию localhost)
//   VITE_DEV_PORT  — порт (по умолчанию 5173)
//   VITE_PROXY_TARGET — адрес БЭКЕНДА (без /api) для dev-прокси, по умолчанию http://localhost:8000
// На сервере/внешнем доступе задайте VITE_DEV_HOST=<ваш-домен> (см. frontend/.env.example).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devHost = env.VITE_DEV_HOST || 'localhost'
  const devPort = Number(env.VITE_DEV_PORT) || 5173
  // Прокси переадресует /api на бэкенд. Это база БЕЗ суффикса /api (иначе будет /api/api).
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
    // Номер релиза для интерфейса (надпись в навигации). В CI/prod задаётся
    // через build-arg `APP_VERSION` (git-тег релиза, см. docker-build.yml/
    // Dockerfile.prod) и имеет приоритет; локально берётся из frontend/.env
    // (предварительный номер), иначе — «dev». Подстановка на этапе сборки.
    define: {
      __APP_VERSION__: JSON.stringify(process.env.APP_VERSION || env.APP_VERSION || "dev"),
    },
    // Тестовые файлы (vitest/RTL) не участвуют в dev-обслуживании и сборке:
    // в окружении без dev-зависимостей (контейнер фронтенда) их импорт «vitest»
    // не резолвится и валит HMR-трансформацию страницы.
    optimizeDeps: {
      entries: ['index.html'],
      exclude: ['vitest'],
    },
    // Прокси запросов к API в режиме разработки: фронтенд на :5173 переадресует /api
    // на бэкенд. Благодаря этому не нужно настраивать CORS/внешний адрес для дев-окружения.
    server: {
      host: true,
      port: devPort,
      allowedHosts: [devHost],
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          secure: false,
        },
      },
      hmr: {
        host: devHost,
        protocol: 'ws'
      }
    }
  }
})
