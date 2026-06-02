<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { renderMarkdown } from '../markdown/renderer'
import { renderMermaidInElement } from '../markdown/mermaid'
import { CHAT_COPY_RESET_MS } from '../config'

const props = defineProps<{
  content: string
  streaming: boolean
}>()

const emit = defineEmits<{
  (e: 'preview-mermaid', source: string): void
}>()

const host = ref<HTMLElement | null>(null)

function handleHostClick(event: MouseEvent): void {
  const target = event.target as HTMLElement | null
  if (!target) return
  const block = target.closest('.mermaid-block') as HTMLElement | null
  if (block && block.dataset.source) {
    emit('preview-mermaid', block.dataset.source)
  }
}
const html = ref('')
let copyResetTimer: number | null = null

function renderNow(): void {
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
     * 水平滚动 + 按钮固定方案：
     * 将 <eq>/<eqn> 内部内容移入一个 inner scroll 容器，overflow-x:auto 转移到该内层。
     * 外层 <eq>/<eqn> 保持 position:relative 但不再自身滚动，
     * 复制按钮 position:absolute 在外层，从而不随内容水平滚动而偏移。
     */
    const inner = document.createElement('div')
    inner.className = 'math-scroll-inner'
    // 将 el 的全部现有子节点移入 inner
    while (el.firstChild) {
      inner.appendChild(el.firstChild)
    }
    el.appendChild(inner)

    const btn = document.createElement('button')
    btn.type = 'button'
    btn.className = 'math-copy-btn'
    btn.title = '复制 LaTeX 公式'
    btn.innerHTML = `<svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2m-6 12h8a2 2 0 0 1 2-2v-8a2 2 0 0 1-2-2h-8a2 2 0 0 1-2 2v8a2 2 0 0 1 2 2z" /></svg>`

    btn.addEventListener('click', async (e) => {
      e.stopPropagation()
      const rawMath = el.getAttribute('data-math') || ''
      const ok = await copyText(rawMath)
      // 在修改 innerHTML/textContent 之前先保存原始内容
      const originalHtml = btn.innerHTML
      btn.textContent = ok ? '已复制' : '复制失败'
      btn.classList.add('copied')
      btn.disabled = true
      setTimeout(() => {
        btn.innerHTML = originalHtml
        btn.classList.remove('copied')
        btn.disabled = false
      }, 1500)
    })

    // 按钮添加到外层（不进入 inner），保证不随公式横向滚动而移动
    el.appendChild(btn)
  })
}

async function enhance(): Promise<void> {
  await nextTick()
  const root = host.value
  if (!root) return
  attachCopyButtons(root)
  attachMathCopyButtons(root)
  if (!props.streaming) {
    await renderMermaidInElement(root)
  }
}

watch(
  () => props.content,
  () => {
    renderNow()
    void enhance()
  },
  { immediate: true },
)

watch(
  () => props.streaming,
  (streaming) => {
    if (!streaming) void enhance()
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
})
</script>

<template>
  <div ref="host" class="markdown-body" v-html="html" @click="handleHostClick" />
</template>
