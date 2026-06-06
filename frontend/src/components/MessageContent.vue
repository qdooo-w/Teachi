<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch, onMounted } from 'vue'

import { renderMarkdown } from '../markdown/renderer'
import { renderMermaidInElement } from '../markdown/mermaid'
import { CHAT_COPY_RESET_MS } from '../config'

const props = defineProps<{
  content: string
  streaming: boolean
}>()

const emit = defineEmits<{
  (e: 'preview-mermaid', source: string): void
  (e: 'preview-image', url: string): void
  (e: 'preview-math', source: string): void
  (e: 'preview-table', html: string): void
}>()

const host = ref<HTMLElement | null>(null)

function handleHostClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  if (!target) return
  
  // 1. Mermaid Block
  const block = target.closest('.mermaid-block') as HTMLElement | null
  if (block && block.dataset.source) {
    emit('preview-mermaid', block.dataset.source)
    return
  }
  
  // 2. Image
  const img = target.closest('img') as HTMLImageElement | null
  if (img) {
    const src = img.getAttribute('src') || ''
    emit('preview-image', src)
    return
  }

  // 3. Math Equation (Display/block eqn first, then inline eq)
  const eqn = target.closest('eqn') as HTMLElement | null
  if (eqn && eqn.dataset.math) {
    emit('preview-math', eqn.dataset.math)
    return
  }
  const eq = target.closest('eq') as HTMLElement | null
  if (eq && eq.dataset.math) {
    emit('preview-math', eq.dataset.math)
    return
  }

  // 4. Table
  const table = target.closest('table') as HTMLTableElement | null
  if (table) {
    emit('preview-table', table.outerHTML)
    return
  }
}
const html = ref('')
let copyResetTimer: number | null = null

function renderNow(): void {
  isUpdatingDOM = true
  try {
    html.value = renderMarkdown(props.content)
  } catch {
    html.value = `<pre>${escapeHtml(props.content)}</pre>`
  }
}

function attachCopyButtons(root: HTMLElement): void {
  const buttons = root.querySelectorAll<HTMLButtonElement>('button[data-copy]')
  buttons.forEach((btn) => {
    if (btn.dataset.copyMounted === '1') return
    btn.dataset.copyMounted = '1'
    btn.addEventListener('click', () => handleCopyClick(btn))
  })
}

async function handleCopyClick(btn: HTMLButtonElement): Promise<void> {
  const block = btn.closest('.code-block')
  const code = block?.querySelector('pre code')
  const text = code?.textContent || ''
  const ok = await copyText(text)
  const originalLabel = '复制'
  btn.textContent = ok ? '已复制' : '复制失败'
  btn.disabled = true
  if (copyResetTimer) window.clearTimeout(copyResetTimer)
  copyResetTimer = window.setTimeout(() => {
    btn.textContent = originalLabel
    btn.disabled = false
  }, CHAT_COPY_RESET_MS)
}

async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      /* fall through */
    }
  }
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}

function attachMathCopyButtons(root: HTMLElement): void {
  const elements = root.querySelectorAll<HTMLElement>('eq[data-math], eqn[data-math]')
  elements.forEach((el) => {
    if (el.dataset.copyMounted === '1') return
    el.dataset.copyMounted = '1'

    /**
     * 水平滚动方案：
     * 将 <eq>/<eqn> 内部内容移入一个 inner scroll 容器，overflow-x:auto 转移到该内层。
     */
    const inner = document.createElement('div')
    inner.className = 'math-scroll-inner'
    while (el.firstChild) {
      inner.appendChild(el.firstChild)
    }
    el.appendChild(inner)
  })
}

let lastValidRange: Range | null = null
let lastValidClone: DocumentFragment | null = null
let savedSelectionOffset: { start: number; end: number } | null = null
let isUpdatingDOM = false

function htmlTableToMarkdown(tableEl: HTMLTableElement): string {
  const rows = Array.from(tableEl.querySelectorAll('tr'))
  const markdownRows = rows.map((row) => {
    const cells = Array.from(row.querySelectorAll('th, td'))
    const cellTexts = cells.map((cell) => {
      return cell.textContent?.trim().replace(/\|/g, '\\|') || ''
    })
    return `| ${cellTexts.join(' | ')} |`
  })

  if (markdownRows.length > 0) {
    const headerCells = rows[0].querySelectorAll('th')
    if (headerCells.length > 0) {
      const separator = `| ${Array(headerCells.length).fill('---').join(' | ')} |`
      markdownRows.splice(1, 0, separator)
    } else {
      const cellsInFirstRow = rows[0].querySelectorAll('td')
      const separator = `| ${Array(cellsInFirstRow.length).fill('---').join(' | ')} |`
      markdownRows.splice(1, 0, separator)
    }
  }
  return markdownRows.join('\n')
}

function handleSelectionChange() {
  if (isUpdatingDOM) return

  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) {
    savedSelectionOffset = null
    return
  }

  const range = selection.getRangeAt(0)
  const root = host.value
  if (!root || !root.contains(range.commonAncestorContainer)) {
    savedSelectionOffset = null
    return
  }

  // 只有当用户划线且包含文本时，才备份选区
  if (selection.toString().trim().length > 0) {
    lastValidRange = range.cloneRange()
    lastValidClone = range.cloneContents()

    // 计算相对于 root 文本内容的字符偏移量
    const preSelectionRange = range.cloneRange()
    preSelectionRange.selectNodeContents(root)
    preSelectionRange.setEnd(range.startContainer, range.startOffset)
    const start = preSelectionRange.toString().length
    const end = start + range.toString().length
    savedSelectionOffset = { start, end }
  } else {
    savedSelectionOffset = null
  }
}

function restoreSelection(): void {
  if (!savedSelectionOffset) return
  const root = host.value
  if (!root) return

  const { start, end } = savedSelectionOffset
  const selection = window.getSelection()
  if (!selection) return

  let charIndex = 0
  const range = document.createRange()
  range.setStart(root, 0)
  range.collapse(true)

  const nodeStack: Node[] = [root]
  let node: Node | undefined
  let foundStart = false
  let foundEnd = false

  while ((node = nodeStack.pop()) && !(foundStart && foundEnd)) {
    if (node.nodeType === Node.TEXT_NODE) {
      const nextCharIndex = charIndex + (node.textContent?.length || 0)
      if (!foundStart && start >= charIndex && start <= nextCharIndex) {
        range.setStart(node, start - charIndex)
        foundStart = true
      }
      if (!foundEnd && end >= charIndex && end <= nextCharIndex) {
        range.setEnd(node, end - charIndex)
        foundEnd = true
      }
      charIndex = nextCharIndex
    } else {
      let i = node.childNodes.length
      while (i--) {
        nodeStack.push(node.childNodes[i])
      }
    }
  }

  if (foundStart && foundEnd) {
    selection.removeAllRanges()
    selection.addRange(range)
  }
}

function handleCopy(e: ClipboardEvent): void {
  const selection = window.getSelection()
  let range = (selection && selection.rangeCount > 0) ? selection.getRangeAt(0) : null
  let clone: DocumentFragment | null = range ? range.cloneContents() : null

  // 1. 判断是否需要从备份选区还原（比如高频重绘下，选区在复制前夕被 Vue v-html 重绘销毁）
  const hasRealSelection = selection && selection.toString().trim().length > 0
  if (!hasRealSelection && !(props.streaming && lastValidClone && lastValidRange)) {
    // 既没有真实划线，也不是在发送过程中具备有效划线备份，说明是非法复制（如点击空白复制），退出
    return
  }

  if ((!range || !clone || clone.textContent?.trim().length === 0) && lastValidClone && lastValidRange) {
    clone = lastValidClone
    range = lastValidRange
  }

  if (!range || !clone) return

  // 2. 判断是否是在单个公式内部双击/直接选中公式
  let closestMath: HTMLElement | null = null
  if (range.commonAncestorContainer.nodeType === Node.TEXT_NODE) {
    closestMath = range.commonAncestorContainer.parentElement?.closest('eq[data-math], eqn[data-math]') || null
  } else if (range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE) {
    closestMath = (range.commonAncestorContainer as HTMLElement).closest('eq[data-math], eqn[data-math]')
  }

  if (closestMath) {
    e.preventDefault()
    const raw = closestMath.getAttribute('data-math') || ''
    const isBlock = closestMath.tagName.toLowerCase() === 'eqn'
    const text = isBlock ? `$$${raw}$$` : `$${raw}$`
    e.clipboardData?.setData('text/plain', text)
    return
  }

  // 3. 跨越多个节点的划线选中（混合公式和表格的处理）
  const container = document.createElement('div')
  container.appendChild(clone.cloneNode(true))

  const hasMath = container.querySelector('eq[data-math], eqn[data-math]')
  const hasTable = container.querySelector('table')

  // 如果没有公式且没有表格
  if (!hasMath && !hasTable) {
    // 如果是因为正在发送（streaming）导致使用了备份，我们需要手动拦截并把纯文本塞入剪贴板以保障发送中的复制稳定性
    if (props.streaming || !selection || selection.rangeCount === 0) {
      e.preventDefault()
      const text = container.innerText || container.textContent || ''
      e.clipboardData?.setData('text/plain', text)
    }
    return
  }

  e.preventDefault()

  // 替换公式节点为 Markdown 原文
  container.querySelectorAll<HTMLElement>('eq[data-math]').forEach((el) => {
    const raw = el.getAttribute('data-math') || ''
    el.textContent = `$${raw}$`
  })
  container.querySelectorAll<HTMLElement>('eqn[data-math]').forEach((el) => {
    const raw = el.getAttribute('data-math') || ''
    el.textContent = `\n$$${raw}$$\n`
  })

  // 替换表格为 Markdown 原文
  container.querySelectorAll<HTMLTableElement>('table').forEach((tableEl) => {
    const markdownTable = htmlTableToMarkdown(tableEl)
    const textNode = document.createTextNode(`\n\n${markdownTable}\n\n`)
    tableEl.parentNode?.replaceChild(textNode, tableEl)
  })

  const plainText = container.innerText || container.textContent || ''
  e.clipboardData?.setData('text/plain', plainText)
}

onMounted(() => {
  const root = host.value
  if (root) {
    root.addEventListener('copy', handleCopy)
    document.addEventListener('selectionchange', handleSelectionChange)
  }
})

async function enhance(): Promise<void> {
  try {
    await nextTick()
    const root = host.value
    if (!root) return
    attachCopyButtons(root)
    attachMathCopyButtons(root)
    if (!props.streaming) {
      await renderMermaidInElement(root)
    }
    restoreSelection()
  } finally {
    isUpdatingDOM = false
  }
}
function throttle<T extends (...args: any[]) => void>(fn: T, delay: number): T {
  let timer: number | null = null
  let lastArgs: any[] | null = null
  return function(this: any, ...args: any[]) {
    if (timer) {
      lastArgs = args
      return
    }
    fn.apply(this, args)
    timer = window.setTimeout(() => {
      timer = null
      if (lastArgs) {
        fn.apply(this, lastArgs)
        lastArgs = null
      }
    }, delay)
  } as unknown as T
}

const throttledRenderAndEnhance = throttle(() => {
  renderNow()
  void enhance()
}, 150)

watch(
  () => props.content,
  () => {
    if (props.streaming) {
      throttledRenderAndEnhance()
    } else {
      renderNow()
      void enhance()
    }
  },
  { immediate: true },
)

watch(
  () => props.streaming,
  (streaming) => {
    if (!streaming) {
      renderNow()
      void enhance()
    }
  },
)

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

onBeforeUnmount(() => {
  if (copyResetTimer) window.clearTimeout(copyResetTimer)
  const root = host.value
  if (root) {
    root.removeEventListener('copy', handleCopy)
  }
  document.removeEventListener('selectionchange', handleSelectionChange)
})
</script>

<template>
  <div ref="host" class="markdown-body" v-html="html" @click="handleHostClick" />
</template>
