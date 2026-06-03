<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { renderMermaidInElement } from '../markdown/mermaid'

interface Props {
  open: boolean
  type: 'image' | 'mermaid'
  source: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'close'): void
}>()

const scale = ref(1.0)
const copied = ref(false)
const copyTimer = ref<number | null>(null)
const mermaidContainer = ref<HTMLElement | null>(null)
const rendering = ref(false)

async function renderDiagram(): Promise<void> {
  if (!props.open || props.type !== 'mermaid' || !props.source) return

  rendering.value = true
  await nextTick()
  const container = mermaidContainer.value
  if (!container) {
    rendering.value = false
    return
  }

  // Clear previous content
  container.innerHTML = ''

  // Create temporary <pre data-lang="mermaid" :data-source="source"></pre>
  const pre = document.createElement('pre')
  pre.setAttribute('data-lang', 'mermaid')
  pre.setAttribute('data-source', props.source)
  pre.textContent = props.source
  // Hide it visually while rendering to prevent flashing source code
  pre.style.opacity = '0'
  pre.style.position = 'absolute'
  container.appendChild(pre)

  try {
    // Call renderMermaidInElement
    await renderMermaidInElement(container)

    // Remove inline style max-width constraint to allow high-definition vector scaling
    const blockEl = container.querySelector('.mermaid-block') as HTMLElement | null
    if (blockEl) {
      blockEl.style.width = '100%'
      blockEl.style.height = '100%'
      blockEl.style.display = 'flex'
      blockEl.style.justifyContent = 'center'
      blockEl.style.alignItems = 'center'
      blockEl.style.background = 'transparent'
      blockEl.style.border = 'none'
      blockEl.style.padding = '0'
      blockEl.style.margin = '0'
    }

    const svgEl = container.querySelector('svg')
    if (svgEl) {
      svgEl.style.maxWidth = '100%'
      svgEl.style.maxHeight = '100%'
      svgEl.style.width = '100%'
      svgEl.style.height = '100%'
    }
  } catch (error) {
    console.error('Failed to render mermaid diagram:', error)
  } finally {
    rendering.value = false
  }
}

watch(
  () => [props.open, props.type, props.source],
  ([open, type]) => {
    if (open) {
      scale.value = 1.0
      if (type === 'mermaid') {
        renderDiagram()
      }
    }
  },
  { immediate: true }
)

function zoomIn(): void {
  scale.value = Math.min(4.0, scale.value + 0.25)
}

function zoomOut(): void {
  scale.value = Math.max(0.25, scale.value - 0.25)
}

function resetZoom(): void {
  scale.value = 1.0
}

async function copySource(): Promise<void> {
  if (props.type !== 'mermaid') return
  try {
    await navigator.clipboard.writeText(props.source)
    copied.value = true
    if (copyTimer.value) {
      window.clearTimeout(copyTimer.value)
    }
    copyTimer.value = window.setTimeout(() => {
      copied.value = false
    }, 1500)
  } catch (err) {
    console.error('Failed to copy text: ', err)
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (props.open && event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (copyTimer.value) {
    window.clearTimeout(copyTimer.value)
  }
})
</script>

<template>
  <div
    class="fixed inset-0 z-[110] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
  >
      <!-- Outer scrollable wrapper -->
      <div
        class="overflow-auto flex items-center justify-center w-full h-full p-8"
        @click="emit('close')"
      >
        <!-- Inner container of the media -->
        <div
          class="modal-card flex items-center justify-center origin-center transition-transform duration-200"
          :style="{ transform: `scale(${scale})` }"
          @click.stop
        >
          <!-- Render Image -->
          <img
            v-if="type === 'image'"
            :src="source"
            alt="Preview"
            class="max-w-full max-h-[85vh] object-contain select-none shadow-2xl rounded-lg"
          />

          <!-- Render Mermaid -->
          <div
            v-else-if="type === 'mermaid'"
            class="relative bg-white p-6 rounded-xl shadow-2xl overflow-hidden w-[85vw] max-w-6xl h-[80vh] flex items-center justify-center"
          >
            <!-- 简洁加载动画 -->
            <div
              v-if="rendering"
              class="absolute inset-0 flex items-center justify-center bg-white/90 z-10"
            >
              <svg class="animate-spin h-8 w-8 text-slate-600" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            </div>

            <!-- 图表容器 -->
            <div
              ref="mermaidContainer"
              class="w-full h-full flex items-center justify-center overflow-auto"
              :class="{ 'opacity-0': rendering }"
            />
          </div>
        </div>
      </div>

      <!-- Floating glassmorphic controls -->
      <div
        class="fixed bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-2 bg-white/10 backdrop-blur-md rounded-full shadow-lg border-0 z-[120] select-none"
        @click.stop
      >
        <!-- Zoom Out Button -->
        <button
          type="button"
          class="flex items-center justify-center p-2 rounded-full text-white/80 hover:text-white hover:bg-white/10 transition-colors border-0 cursor-pointer"
          title="缩小 (Zoom Out)"
          :disabled="scale <= 0.25"
          @click="zoomOut"
        >
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4" />
          </svg>
        </button>

        <!-- Zoom Level indicator / Reset Button -->
        <button
          type="button"
          class="flex items-center justify-center px-3 py-1 rounded-full text-white/80 hover:text-white hover:bg-white/10 transition-colors border-0 cursor-pointer font-sans text-sm font-medium"
          title="重置缩放 (Reset)"
          @click="resetZoom"
        >
          {{ Math.round(scale * 100) }}%
        </button>

        <!-- Zoom In Button -->
        <button
          type="button"
          class="flex items-center justify-center p-2 rounded-full text-white/80 hover:text-white hover:bg-white/10 transition-colors border-0 cursor-pointer"
          title="放大 (Zoom In)"
          :disabled="scale >= 4.0"
          @click="zoomIn"
        >
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
        </button>

        <!-- Divider line -->
        <div v-if="type === 'mermaid'" class="w-px h-5 bg-white/20 mx-1" />

        <!-- Copy Source Button (Mermaid only) -->
        <button
          v-if="type === 'mermaid'"
          type="button"
          class="flex items-center justify-center p-2 rounded-full text-white/80 hover:text-white hover:bg-white/10 transition-colors border-0 cursor-pointer"
          :title="copied ? '已复制' : '复制 Mermaid 源码'"
          @click="copySource"
        >
          <svg v-if="!copied" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 002-2h2a2 2 0 002-2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
          </svg>
          <svg v-else class="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </button>

        <!-- Divider line -->
        <div class="w-px h-5 bg-white/20 mx-1" />

        <!-- Close Button -->
        <button
          type="button"
          class="flex items-center justify-center p-2 rounded-full text-white/80 hover:text-white hover:bg-white/10 transition-colors border-0 cursor-pointer"
          title="关闭 (Close)"
          @click="emit('close')"
        >
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  </template>
