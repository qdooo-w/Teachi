let mermaidModule: typeof import('mermaid').default | null = null
let mermaidInitPromise: Promise<typeof import('mermaid').default> | null = null
let renderCounter = 0

async function loadMermaid(): Promise<typeof import('mermaid').default> {
  if (mermaidModule) return mermaidModule
  if (!mermaidInitPromise) {
    mermaidInitPromise = import('mermaid').then((mod) => {
      const instance = mod.default
      instance.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'default',
        fontFamily: 'inherit',
      })
      mermaidModule = instance
      return instance
    })
  }
  return mermaidInitPromise
}

/**
 * 渲染 root 内所有 Mermaid 占位代码块。
 * 仅替换 <pre data-lang="mermaid"> 子树，对已处理节点跳过。
 */
export async function renderMermaidInElement(root: HTMLElement): Promise<void> {
  const nodes = root.querySelectorAll<HTMLElement>('pre[data-lang="mermaid"]')
  if (nodes.length === 0) return

  const mermaid = await loadMermaid()

  for (const node of Array.from(nodes)) {
    if (node.dataset.rendered === 'mermaid') continue
    const source = (node.dataset.source || node.textContent || '').trim()
    if (!source) continue

    const id = `mermaid-svg-${++renderCounter}`
    try {
      const { svg } = await mermaid.render(id, source)
      const container = document.createElement('div')
      container.className = 'mermaid-block cursor-pointer hover:opacity-90 transition-opacity'
      container.dataset.rendered = 'mermaid'
      container.dataset.source = source
      container.innerHTML = svg
      node.replaceWith(container)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const fallback = document.createElement('div')
      fallback.className = 'mermaid-error'
      fallback.dataset.rendered = 'mermaid-error'
      const errorLine = document.createElement('div')
      errorLine.className = 'mermaid-error-message'
      errorLine.textContent = `Mermaid 渲染失败：${message}`
      const pre = document.createElement('pre')
      pre.textContent = source
      fallback.append(errorLine, pre)
      node.replaceWith(fallback)
    }
  }
}
