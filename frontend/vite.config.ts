import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_DEV_API_PROXY_TARGET || 'http://localhost:8000'

  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/auth': backendTarget,
        '/loop': backendTarget,
        '/users': backendTarget,
        '/projects': backendTarget,
        '/sessions': backendTarget,
        '/messages': backendTarget,
        '/tools': backendTarget,
        '/health': backendTarget,
      },
    },
  }
})
