/// <reference types="vite/client" />

declare module 'markdown-it-texmath' {
  import type { PluginWithOptions } from 'markdown-it'
  const plugin: PluginWithOptions<Record<string, unknown>>
  export default plugin
}

