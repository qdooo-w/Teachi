<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { renderMermaidInElement } from '../markdown/mermaid'
import katex from 'katex'

interface Props {
  open: boolean
  type: 'image' | 'mermaid' | 'math' | 'table'
  source: string
  index: number
  highlight?: boolean
  staggerIndex?: number
  initialX?: number
  initialY?: number
  initialWidth?: number
  initialHeight?: number
  dockLeft?: boolean
  dockRight?: boolean
  dockTop?: boolean
  dockBottom?: boolean
  relX?: number
  relY?: number
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'focus'): void
  (e: 'minimize'): void
  (e: 'update-rect', rect: {
    x: number
    y: number
    width: number
    height: number
    dockLeft?: boolean
    dockRight?: boolean
    dockTop?: boolean
    dockBottom?: boolean
    relX?: number
    relY?: number
  }): void
}>()

const scale = ref(1.0)
const offsetX = ref(0)
const offsetY = ref(0)
const isDragging = ref(false)
const copied = ref(false)
const copyTimer = ref<number | null>(null)
const mermaidContainer = ref<HTMLElement | null>(null)
const rendering = ref(false)

// Loading state for smooth entry
const loaded = ref(false)
const showLoader = ref(false)
const isInitialTransitionActive = ref(true)
let loaderTimeout: number | null = null

function clearLoaderTimeout(): void {
  if (loaderTimeout) {
    clearTimeout(loaderTimeout)
    loaderTimeout = null
  }
  showLoader.value = false
}

// Window size and position state
const windowWidth = ref(props.initialWidth || 600)
const windowHeight = ref(props.initialHeight || 650)
const windowX = ref(props.initialX || 100)
const windowY = ref(props.initialY || 100)
const isDraggingWindow = ref(false)
const isResizing = ref(false)

const mathContainer = ref<HTMLElement | null>(null)
const tableContainer = ref<HTMLElement | null>(null)

const currentDockLeft = ref(props.dockLeft ?? false)
const currentDockRight = ref(props.dockRight ?? false)
const currentDockTop = ref(props.dockTop ?? false)
const currentDockBottom = ref(props.dockBottom ?? false)
const currentRelX = ref(props.relX ?? 0.5)
const currentRelY = ref(props.relY ?? 0.5)

function updateRectEmit(): void {
  const isLeft = windowX.value <= 1
  const isRight = windowX.value >= window.innerWidth - windowWidth.value - 1
  const isTop = windowY.value <= 1
  const isBottom = windowY.value >= window.innerHeight - windowHeight.value - 1

  const denomX = window.innerWidth - windowWidth.value
  const rX = denomX > 0 ? Math.max(0, Math.min(1, windowX.value / denomX)) : 0

  const denomY = window.innerHeight - windowHeight.value
  const rY = denomY > 0 ? Math.max(0, Math.min(1, windowY.value / denomY)) : 0

  currentDockLeft.value = isLeft
  currentDockRight.value = isRight
  currentDockTop.value = isTop
  currentDockBottom.value = isBottom

  let emitRelX: number | undefined = undefined
  let emitRelY: number | undefined = undefined

  if (isTop || isBottom) {
    if (!isLeft && !isRight) {
      emitRelX = rX
    }
  } else if (isLeft || isRight) {
    if (!isTop && !isBottom) {
      emitRelY = rY
    }
  } else {
    emitRelX = rX
    emitRelY = rY
  }

  if (emitRelX !== undefined) {
    currentRelX.value = emitRelX
  } else if (!isLeft && !isRight) {
    currentRelX.value = rX
  }

  if (emitRelY !== undefined) {
    currentRelY.value = emitRelY
  } else if (!isTop && !isBottom) {
    currentRelY.value = rY
  }

  emit('update-rect', {
    x: windowX.value,
    y: windowY.value,
    width: windowWidth.value,
    height: windowHeight.value,
    dockLeft: isLeft,
    dockRight: isRight,
    dockTop: isTop,
    dockBottom: isBottom,
    relX: emitRelX,
    relY: emitRelY
  })
}

async function renderContent(): Promise<void> {
  if (!props.open || !props.source) return

  rendering.value = true
  await nextTick()

  if (props.type === 'mermaid') {
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
    pre.style.opacity = '0'
    pre.style.position = 'absolute'
    container.appendChild(pre)

    try {
      await renderMermaidInElement(container)

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

        // Auto-fit window to Mermaid diagram dimensions
        const viewBox = svgEl.getAttribute('viewBox')
        if (viewBox) {
          const parts = viewBox.split(' ')
          if (parts.length === 4) {
            const w = parseFloat(parts[2])
            const h = parseFloat(parts[3])
            if (w > 0 && h > 0) {
              if (props.initialWidth === undefined || props.initialHeight === undefined) {
                const maxW = Math.min(900, window.innerWidth * 0.85)
                const maxH = Math.min(700, window.innerHeight * 0.75)
                let targetW = w + 48 // Add padding
                let targetH = h + 48
                
                const ratio = w / h
                if (targetW > maxW) {
                  targetW = maxW
                  targetH = targetW / ratio
                }
                if (targetH > maxH) {
                  targetH = maxH
                  targetW = targetH * ratio
                }
                
                windowWidth.value = Math.max(380, Math.round(targetW))
                windowHeight.value = Math.round(targetH) + 36 // Title bar height
                
                // Center the window strictly inside bounds
                const baseLeft = (window.innerWidth - windowWidth.value) / 2
                const baseTop = (window.innerHeight - windowHeight.value) / 2
                const stagger = (props.staggerIndex || 0) * 25
                windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, baseLeft + stagger))
                windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, baseTop + stagger))
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Failed to render mermaid diagram:', error)
    } finally {
      rendering.value = false
      loaded.value = true
      clearLoaderTimeout()
      updateRectEmit()
    }
  } else if (props.type === 'math') {
    const container = mathContainer.value
    if (!container) {
      rendering.value = false
      return
    }
    try {
      container.innerHTML = ''
      katex.render(props.source, container, {
        displayMode: true,
        throwOnError: false,
        strict: 'ignore',
        output: 'html'
      })
      
      // Auto-fit window size for math formula
      if (props.initialWidth === undefined || props.initialHeight === undefined) {
        windowWidth.value = Math.min(650, Math.max(450, Math.round(window.innerWidth * 0.5)))
        windowHeight.value = 240
        
        // Center the window strictly inside bounds
        const baseLeft = (window.innerWidth - windowWidth.value) / 2
        const baseTop = (window.innerHeight - windowHeight.value) / 2
        const stagger = (props.staggerIndex || 0) * 25
        windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, baseLeft + stagger))
        windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, baseTop + stagger))
      }
    } catch (err) {
      console.error('Failed to render math formula:', err)
    } finally {
      rendering.value = false
      loaded.value = true
      clearLoaderTimeout()
      updateRectEmit()
    }
  } else if (props.type === 'table') {
    const container = tableContainer.value
    if (!container) {
      rendering.value = false
      return
    }
    try {
      container.innerHTML = props.source
      
      // Auto-fit window size for table
      if (props.initialWidth === undefined || props.initialHeight === undefined) {
        windowWidth.value = Math.min(850, Math.max(550, Math.round(window.innerWidth * 0.7)))
        windowHeight.value = Math.min(500, Math.max(350, Math.round(window.innerHeight * 0.5)))
        
        // Center the window strictly inside bounds
        const baseLeft = (window.innerWidth - windowWidth.value) / 2
        const baseTop = (window.innerHeight - windowHeight.value) / 2
        const stagger = (props.staggerIndex || 0) * 25
        windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, baseLeft + stagger))
        windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, baseTop + stagger))
      }
    } catch (err) {
      console.error('Failed to render table:', err)
    } finally {
      rendering.value = false
      loaded.value = true
      clearLoaderTimeout()
      updateRectEmit()
    }
  }
}

watch(
  () => [props.open, props.type, props.source],
  ([open, type]) => {
    if (open) {
      scale.value = 1.0
      offsetX.value = 0
      offsetY.value = 0
      loaded.value = false
      isInitialTransitionActive.value = true
      
      clearLoaderTimeout()
      loaderTimeout = window.setTimeout(() => {
        if (!loaded.value) {
          showLoader.value = true
        }
      }, 200)

      if (type !== 'image') {
        renderContent()
      }
    }
  },
  { immediate: true }
)

// Remove transition class after the window entry finishes to avoid drag lag
watch(loaded, (val) => {
  if (val) {
    setTimeout(() => {
      isInitialTransitionActive.value = false
    }, 400)
  }
})

function zoomIn(): void {
  scale.value = Math.min(4.0, scale.value + 0.25)
}

function zoomOut(): void {
  scale.value = Math.max(0.25, scale.value - 0.25)
}

function resetZoom(): void {
  scale.value = 1.0
  offsetX.value = 0
  offsetY.value = 0
}

function handleWheel(e: WheelEvent): void {
  const zoomStep = 0.1
  if (e.deltaY < 0) {
    scale.value = Math.min(4.0, Number((scale.value + zoomStep).toFixed(2)))
  } else {
    scale.value = Math.max(0.25, Number((scale.value - zoomStep).toFixed(2)))
  }
}

// Image load event to auto-fit window boundaries
function handleImageLoad(e: Event): void {
  const img = e.target as HTMLImageElement
  if (!img) return
  const w = img.naturalWidth
  const h = img.naturalHeight
  
  // Only run auto-fit if we don't have initial coordinates/dimensions
  if (props.initialWidth === undefined || props.initialHeight === undefined) {
    if (w > 0 && h > 0) {
      const maxW = Math.min(800, window.innerWidth * 0.8)
      const maxH = Math.min(600, window.innerHeight * 0.7)
      let targetW = w
      let targetH = h
      
      const ratio = w / h
      if (targetW > maxW) {
        targetW = maxW
        targetH = targetW / ratio
      }
      if (targetH > maxH) {
        targetH = maxH
        targetW = targetH * ratio
      }
      
      windowWidth.value = Math.max(380, Math.round(targetW))
      windowHeight.value = Math.round(targetH) + 36 // Title bar height
      
      // Center the window
      const baseLeft = (window.innerWidth - windowWidth.value) / 2
      const baseTop = (window.innerHeight - windowHeight.value) / 2
      const stagger = (props.staggerIndex || 0) * 25
      windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, baseLeft + stagger))
      windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, baseTop + stagger))
    }
  }
  loaded.value = true
  clearLoaderTimeout()
  updateRectEmit()
}

function handleImageError(): void {
  loaded.value = true
  clearLoaderTimeout()
  updateRectEmit()
}

// Media Panning (inner dragging)
let startX = 0
let startY = 0
let startOffsetX = 0
let startOffsetY = 0

function handleDragStart(e: MouseEvent | TouchEvent): void {
  if (e instanceof MouseEvent && e.button !== 0) return

  isDragging.value = true
  
  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const clientY = e instanceof MouseEvent ? e.clientY : e.touches[0].clientY
  
  startX = clientX
  startY = clientY
  startOffsetX = offsetX.value
  startOffsetY = offsetY.value

  if (e instanceof MouseEvent) {
    document.addEventListener('mousemove', handleDragMove)
    document.addEventListener('mouseup', handleDragEnd)
  } else {
    document.addEventListener('touchmove', handleDragMove, { passive: false })
    document.addEventListener('touchend', handleDragEnd)
  }
}

function handleDragMove(e: MouseEvent | TouchEvent): void {
  if (!isDragging.value) return

  if (e instanceof TouchEvent) {
    e.preventDefault()
  }

  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const clientY = e instanceof MouseEvent ? e.clientY : e.touches[0].clientY

  const dx = clientX - startX
  const dy = clientY - startY

  offsetX.value = startOffsetX + dx
  offsetY.value = startOffsetY + dy
}

function handleDragEnd(): void {
  isDragging.value = false
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
  document.removeEventListener('touchmove', handleDragMove)
  document.removeEventListener('touchend', handleDragEnd)
}

// Window Dragging (outer window translation)
let windowDragStartX = 0
let windowDragStartY = 0
let windowDragStartLeft = 0
let windowDragStartTop = 0

function handleWindowDragStart(e: MouseEvent | TouchEvent): void {
  if (e instanceof MouseEvent && e.button !== 0) return

  isDraggingWindow.value = true

  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const clientY = e instanceof MouseEvent ? e.clientY : e.touches[0].clientY

  windowDragStartX = clientX
  windowDragStartY = clientY
  windowDragStartLeft = windowX.value
  windowDragStartTop = windowY.value

  if (e instanceof MouseEvent) {
    document.addEventListener('mousemove', handleWindowDragMove)
    document.addEventListener('mouseup', handleWindowDragEnd)
  } else {
    document.addEventListener('touchmove', handleWindowDragMove, { passive: false })
    document.addEventListener('touchend', handleWindowDragEnd)
  }
}

function handleWindowDragMove(e: MouseEvent | TouchEvent): void {
  if (!isDraggingWindow.value) return

  if (e instanceof TouchEvent) {
    e.preventDefault()
  }

  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const clientY = e instanceof MouseEvent ? e.clientY : e.touches[0].clientY

  const dx = clientX - windowDragStartX
  const dy = clientY - windowDragStartY

  // Constrain coordinates completely inside the viewport bounds
  windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, windowDragStartLeft + dx))
  windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, windowDragStartTop + dy))
}

// Window Resizing
let resizeDragStartX = 0
let resizeDragStartY = 0
let resizeStartWidth = 0
let resizeStartHeight = 0

function handleResizeStart(e: MouseEvent | TouchEvent): void {
  if (e instanceof MouseEvent && e.button !== 0) return

  isResizing.value = true

  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const clientY = e instanceof MouseEvent ? e.clientY : e.touches[0].clientY

  resizeDragStartX = clientX
  resizeDragStartY = clientY
  resizeStartWidth = windowWidth.value
  resizeStartHeight = windowHeight.value

  if (e instanceof MouseEvent) {
    document.addEventListener('mousemove', handleResizeMove)
    document.addEventListener('mouseup', handleResizeEnd)
  } else {
    document.addEventListener('touchmove', handleResizeMove, { passive: false })
    document.addEventListener('touchend', handleResizeEnd)
  }
}

function handleResizeMove(e: MouseEvent | TouchEvent): void {
  if (!isResizing.value) return

  if (e instanceof TouchEvent) {
    e.preventDefault()
  }

  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0].clientX
  const clientY = e instanceof MouseEvent ? e.clientY : e.touches[0].clientY

  const dx = clientX - resizeDragStartX
  const dy = clientY - resizeDragStartY

  // Limit window size (min 380x300 or 250x120 for math, max fit screen boundaries)
  const minW = props.type === 'math' ? 250 : 380
  const minH = props.type === 'math' ? 120 : 300
  windowWidth.value = Math.max(minW, Math.min(window.innerWidth - windowX.value - 10, resizeStartWidth + dx))
  windowHeight.value = Math.max(minH, Math.min(window.innerHeight - windowY.value - 10, resizeStartHeight + dy))
}

function handleResizeEnd(): void {
  isResizing.value = false
  document.removeEventListener('mousemove', handleResizeMove)
  document.removeEventListener('mouseup', handleResizeEnd)
  document.removeEventListener('touchmove', handleResizeMove)
  document.removeEventListener('touchend', handleResizeEnd)
  
  updateRectEmit()
}

function handleWindowDragEnd(): void {
  isDraggingWindow.value = false
  document.removeEventListener('mousemove', handleWindowDragMove)
  document.removeEventListener('mouseup', handleWindowDragEnd)
  document.removeEventListener('touchmove', handleWindowDragMove)
  document.removeEventListener('touchend', handleWindowDragEnd)
  
  updateRectEmit()
}

async function copySource(): Promise<void> {
  if (props.type !== 'mermaid' && props.type !== 'math') return
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

function clampWindowPosition(): void {
  windowWidth.value = Math.min(windowWidth.value, window.innerWidth)
  windowHeight.value = Math.min(windowHeight.value, window.innerHeight)
  windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, windowX.value))
  windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, windowY.value))
}

function restorePosition(): void {
  if (props.initialWidth !== undefined) {
    windowWidth.value = Math.min(props.initialWidth, window.innerWidth)
  } else {
    const isMobile = window.innerWidth < 768
    windowWidth.value = isMobile ? Math.round(window.innerWidth * 0.9) : 600
  }

  if (props.initialHeight !== undefined) {
    windowHeight.value = Math.min(props.initialHeight, window.innerHeight)
  } else {
    const isMobile = window.innerWidth < 768
    windowHeight.value = isMobile ? Math.round(window.innerHeight * 0.7) : 650
  }

  if (currentDockLeft.value) {
    windowX.value = 0
  } else if (currentDockRight.value) {
    windowX.value = Math.max(0, window.innerWidth - windowWidth.value)
  } else if (props.relX !== undefined) {
    const denomX = window.innerWidth - windowWidth.value
    windowX.value = denomX > 0 ? Math.max(0, Math.min(denomX, Math.round(props.relX * denomX))) : 0
  } else if (props.initialX !== undefined) {
    windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, props.initialX))
  } else {
    const baseLeft = (window.innerWidth - windowWidth.value) / 2
    const stagger = (props.staggerIndex || 0) * 25
    windowX.value = Math.max(0, Math.min(window.innerWidth - windowWidth.value, baseLeft + stagger))
  }

  if (currentDockTop.value) {
    windowY.value = 0
  } else if (currentDockBottom.value) {
    windowY.value = Math.max(0, window.innerHeight - windowHeight.value)
  } else if (props.relY !== undefined) {
    const denomY = window.innerHeight - windowHeight.value
    windowY.value = denomY > 0 ? Math.max(0, Math.min(denomY, Math.round(props.relY * denomY))) : 0
  } else if (props.initialY !== undefined) {
    windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, props.initialY))
  } else {
    const baseTop = (window.innerHeight - windowHeight.value) / 2
    const stagger = (props.staggerIndex || 0) * 25
    windowY.value = Math.max(0, Math.min(window.innerHeight - windowHeight.value, baseTop + stagger))
  }

  const denomX = window.innerWidth - windowWidth.value
  currentRelX.value = props.relX ?? (denomX > 0 ? windowX.value / denomX : 0.5)
  const denomY = window.innerHeight - windowHeight.value
  currentRelY.value = props.relY ?? (denomY > 0 ? windowY.value / denomY : 0.5)
}

function handleViewportResize(): void {
  windowWidth.value = Math.min(windowWidth.value, window.innerWidth)
  windowHeight.value = Math.min(windowHeight.value, window.innerHeight)

  if (currentDockLeft.value) {
    windowX.value = 0
  } else if (currentDockRight.value) {
    windowX.value = Math.max(0, window.innerWidth - windowWidth.value)
  } else {
    const denomX = window.innerWidth - windowWidth.value
    windowX.value = denomX > 0 ? Math.max(0, Math.min(denomX, Math.round(currentRelX.value * denomX))) : 0
  }

  if (currentDockTop.value) {
    windowY.value = 0
  } else if (currentDockBottom.value) {
    windowY.value = Math.max(0, window.innerHeight - windowHeight.value)
  } else {
    const denomY = window.innerHeight - windowHeight.value
    windowY.value = denomY > 0 ? Math.max(0, Math.min(denomY, Math.round(currentRelY.value * denomY))) : 0
  }

  clampWindowPosition()
  updateRectEmit()
}

function handleKeydown(event: KeyboardEvent): void {
  if (props.open && event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', handleViewportResize)
  
  nextTick(() => {
    restorePosition()
  })

  // Safety fallback: force fade-in after 1.5 seconds if loading hangs
  setTimeout(() => {
    if (!loaded.value) {
      loaded.value = true
      clearLoaderTimeout()
      updateRectEmit()
    }
  }, 1500)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleViewportResize)
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
  document.removeEventListener('touchmove', handleDragMove)
  document.removeEventListener('touchend', handleDragEnd)
  document.removeEventListener('mousemove', handleWindowDragMove)
  document.removeEventListener('mouseup', handleWindowDragEnd)
  document.removeEventListener('touchmove', handleWindowDragMove)
  document.removeEventListener('touchend', handleWindowDragEnd)
  document.removeEventListener('mousemove', handleResizeMove)
  document.removeEventListener('mouseup', handleResizeEnd)
  document.removeEventListener('touchmove', handleResizeMove)
  document.removeEventListener('touchend', handleResizeEnd)
  if (copyTimer.value) {
    window.clearTimeout(copyTimer.value)
  }
  if (loaderTimeout) {
    window.clearTimeout(loaderTimeout)
  }
})
</script>

<template>
  <!-- Sleek centered loading tag while window is preparing its dimensions -->
  <Transition name="fade">
    <div v-if="showLoader" class="fixed inset-0 z-[125] flex items-center justify-center pointer-events-none">
      <div class="bg-neutral-900/85 backdrop-blur-md text-white px-4 py-2.5 rounded-full flex items-center gap-2.5 shadow-xl text-xs font-medium border border-white/10">
        <svg class="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <span style="display: inline-block; font-size: 12px; transform: scale(0.9); transform-origin: left center;">载入预览...</span>
      </div>
    </div>
  </Transition>

  <!-- Main Draggable and Resizable Window -->
  <div
    class="media-preview-window fixed z-[120] bg-white border border-neutral-200 shadow-lg rounded-2xl flex flex-col overflow-hidden select-none"
    :class="{
      'opacity-0 scale-95 pointer-events-none': !loaded,
      'opacity-100 scale-100': loaded,
      'border-indigo-500 ring-4 ring-indigo-500/20': highlight
    }"
    :style="{
      top: windowY + 'px',
      left: windowX + 'px',
      width: windowWidth + 'px',
      height: windowHeight + 'px',
      transition: (loaded && isInitialTransitionActive) ? 'opacity 350ms cubic-bezier(0.16, 1, 0.3, 1), transform 350ms cubic-bezier(0.16, 1, 0.3, 1)' : 'border-color 300ms ease, box-shadow 300ms ease'
    }"
    @mousedown="emit('focus')"
    @touchstart="emit('focus')"
  >
    <!-- Window Title Bar -->
    <div
      class="h-9 bg-neutral-50 border-b border-neutral-100 flex items-center justify-between px-3 cursor-move select-none flex-shrink-0"
      @mousedown="handleWindowDragStart"
      @touchstart="handleWindowDragStart"
    >
      <div class="flex items-center gap-1.5 font-medium text-xs text-neutral-700 min-w-0 flex-1">
        <span style="display: inline-block; font-size: 12px; transform: scale(0.9); transform-origin: left center; white-space: nowrap;" class="truncate">
          [#{{ index }}] {{ type === 'image' ? '图片预览' : (type === 'mermaid' ? 'Mermaid 架构图' : (type === 'math' ? 'LaTeX 数学公式' : '数据表格预览')) }}
        </span>
      </div>

      <!-- Controls inside title bar -->
      <div class="flex items-center gap-1 flex-shrink-0" @mousedown.stop="emit('focus')" @touchstart.stop="emit('focus')">
        <!-- Zoom Out -->
        <button
          type="button"
          class="p-0.5 hover:bg-neutral-200/70 rounded text-neutral-600 hover:text-neutral-900 transition-colors border-0 cursor-pointer flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed"
          title="缩小 (Zoom Out)"
          :disabled="scale <= 0.25"
          @click="zoomOut"
        >
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4" />
          </svg>
        </button>

        <!-- Scale Level / Reset -->
        <button
          type="button"
          class="px-1.5 py-0.5 hover:bg-neutral-200/70 rounded font-medium text-neutral-600 hover:text-neutral-900 transition-colors border-0 cursor-pointer flex items-center justify-center"
          title="重置缩放 (Reset)"
          @click="resetZoom"
        >
          <span style="display: inline-block; font-size: 12px; transform: scale(0.9); transform-origin: center; white-space: nowrap;">
            {{ Math.round(scale * 100) }}%
          </span>
        </button>

        <!-- Zoom In -->
        <button
          type="button"
          class="p-0.5 hover:bg-neutral-200/70 rounded text-neutral-600 hover:text-neutral-900 transition-colors border-0 cursor-pointer flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed"
          title="放大 (Zoom In)"
          :disabled="scale >= 4.0"
          @click="zoomIn"
        >
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
        </button>

        <!-- Divider -->
        <div v-if="type === 'mermaid' || type === 'math'" class="w-px h-3 bg-neutral-200 mx-0.5 flex-shrink-0" />

        <!-- Copy Source (Mermaid / Math only) -->
        <button
          v-if="type === 'mermaid' || type === 'math'"
          type="button"
          class="p-0.5 hover:bg-neutral-200/70 rounded text-neutral-600 hover:text-neutral-900 transition-colors border-0 cursor-pointer flex items-center justify-center"
          :title="copied ? '已复制' : (type === 'mermaid' ? '复制 Mermaid 源码' : '复制 LaTeX 公式')"
          @click="copySource"
        >
          <svg v-if="!copied" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 002-2h2a2 2 0 002-2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
          </svg>
          <svg v-else class="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </button>

        <!-- Minimize / Suspend -->
        <button
          type="button"
          class="p-0.5 hover:bg-neutral-200/70 rounded text-neutral-500 hover:text-neutral-900 transition-colors border-0 cursor-pointer flex items-center justify-center"
          title="挂起 (Minimize)"
          @click="emit('minimize')"
        >
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4" />
          </svg>
        </button>

        <!-- Divider -->
        <div class="w-px h-3 bg-neutral-200 mx-0.5 flex-shrink-0" />

        <!-- Close -->
        <button
          type="button"
          class="p-0.5 hover:bg-red-50 hover:text-red-600 rounded text-neutral-500 transition-colors border-0 cursor-pointer flex items-center justify-center"
          title="关闭 (Close)"
          @click="emit('close')"
        >
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Content Area -->
    <div
      class="flex-1 relative bg-neutral-50/50 overflow-hidden flex items-center justify-center"
      @wheel.prevent="handleWheel"
    >
      <div
        class="modal-card flex items-center justify-center origin-center select-none w-full h-full"
        :class="{
          'cursor-grab': !isDragging,
          'cursor-grabbing': isDragging,
          'transition-transform duration-200': !isDragging
        }"
        :style="{ transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})` }"
        @mousedown="handleDragStart"
        @touchstart="handleDragStart"
        @click.stop
      >
        <!-- Render Image -->
        <img
          v-if="type === 'image'"
          :src="source"
          alt="Preview"
          draggable="false"
          class="w-full h-full object-contain select-none shadow-lg rounded-lg"
          @load="handleImageLoad"
          @error="handleImageError"
        />

        <!-- Render Mermaid -->
        <div
          v-else-if="type === 'mermaid'"
          class="relative bg-white rounded-xl shadow-sm overflow-hidden w-full h-full flex items-center justify-center"
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

        <!-- Render Math -->
        <div
          v-else-if="type === 'math'"
          class="relative bg-white rounded-xl shadow-sm overflow-auto w-full h-full flex items-center justify-center p-6"
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

          <div
            ref="mathContainer"
            class="w-full text-center overflow-x-auto text-neutral-800"
            :class="{ 'opacity-0': rendering }"
            @mousedown.stop
            @touchstart.stop
          />
        </div>

        <!-- Render Table -->
        <div
          v-else-if="type === 'table'"
          class="relative bg-white rounded-xl shadow-sm overflow-auto w-full h-full p-6 markdown-body"
          style="cursor: default;"
          @mousedown.stop
          @touchstart.stop
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

          <div
            ref="tableContainer"
            class="w-full overflow-x-auto"
            :class="{ 'opacity-0': rendering }"
          />
        </div>
      </div>
    </div>

    <!-- Resize Handle -->
    <div
      class="absolute bottom-0 right-0 w-5 h-5 cursor-se-resize flex items-end justify-end p-0.5 z-[130] group/resize"
      @mousedown="handleResizeStart"
      @touchstart="handleResizeStart"
    >
      <svg class="w-3 h-3 text-neutral-400 group-hover/resize:text-neutral-600 transition-colors" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <line x1="6" y1="18" x2="18" y2="6"></line>
        <line x1="12" y1="18" x2="18" y2="12"></line>
      </svg>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
