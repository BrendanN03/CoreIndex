import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // process.env wins so `npm run dev` / dev-stack.mjs can override .env.local port.
  const proxyTarget =
    process.env.VITE_API_PROXY_TARGET || env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8010'

  return {
    plugins: [react()],
    server: {
      proxy: {
        // Same-origin in dev so CORS/credentials never block auth or API calls.
        '/coreindex-api': {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/coreindex-api/, ''),
          // Default proxy timeouts are too low for GPU factoring and can wedge the one-click demo.
          timeout: 7_200_000,
          proxyTimeout: 7_200_000,
        },
      },
    },
  }
})
