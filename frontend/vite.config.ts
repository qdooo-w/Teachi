import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import type { IncomingMessage } from 'node:http'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_DEV_API_PROXY_TARGET || 'http://localhost:8000'

  // /projects 与 /sessions 既是后端 API 前缀，也是前端 SPA 路由前缀。
  // 浏览器刷新 /projects/xxx 时，请求带 Accept: text/html，应该走 SPA fallback 拿 index.html，
  // 而不是被代理到后端（后端这些路径只支持 PATCH/DELETE，会 404/405）。
  // fetch / XHR 调用 Accept 通常是 */* 或 application/json，那些继续走代理。
  const isHtmlNavigation = (req: IncomingMessage): boolean =>
    req.method === 'GET' && (req.headers.accept ?? '').includes('text/html')

  const spaFallback = {
    target: backendTarget,
    bypass(req: IncomingMessage) {
      if (isHtmlNavigation(req)) return '/index.html'
    },
  }

  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/auth': backendTarget,
        '/loop': backendTarget,
        '/users': backendTarget,
        '/projects': spaFallback,
        '/sessions': spaFallback,
        '/messages': backendTarget,
        '/tools': backendTarget,
        '/health': backendTarget,
      },
    },
  }
})
