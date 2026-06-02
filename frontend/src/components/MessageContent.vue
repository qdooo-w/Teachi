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

async function enhance(): Promise<void> {
  await nextTick()
  const root = host.value
  if (!root) return
  attachCopyButtons(root)
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
