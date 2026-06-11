<script setup lang="ts">
import { computed, nextTick, ref, watch, type ComponentPublicInstance } from 'vue'

interface ScrollNodeChainItem {
  id: string
  label: string
}

const NODE_GAP_PX = 28
const TOOLTIP_MARGIN_PX = 10

const props = defineProps<{
  nodes: ScrollNodeChainItem[]
  virtualIndex: number
}>()

const emit = defineEmits<{
  seek: [index: number]
  hover: [index: number]
}>()

const viewportEl = ref<HTMLElement | null>(null)
const nodeElements = new Map<number, HTMLElement>()
const hoveredIndex = ref<number | null>(null)
const tooltipTop = ref(0)

const currentIndex = computed(() => {
  if (props.nodes.length === 0) return -1
  return Math.max(0, Math.min(props.nodes.length - 1, Math.round(props.virtualIndex)))
})

const trackTransform = computed(() => {
  const center = (viewportEl.value?.clientHeight ?? 304) / 2
  return `translateY(${center - props.virtualIndex * NODE_GAP_PX}px)`
})

const tooltipLabel = computed(() => {
  if (hoveredIndex.value === null) return ''
  return props.nodes[hoveredIndex.value]?.label || '...'
})

function setNodeElement(index: number, el: Element | ComponentPublicInstance | null): void {
  if (el instanceof HTMLElement) {
    nodeElements.set(index, el)
  } else {
    nodeElements.delete(index)
  }
}

function updateTooltipPosition(): void {
  if (hoveredIndex.value === null || !viewportEl.value) return
  const node = nodeElements.get(hoveredIndex.value)
  if (!node) return

  const viewportRect = viewportEl.value.getBoundingClientRect()
  const nodeRect = node.getBoundingClientRect()
  const center = nodeRect.top + nodeRect.height / 2 - viewportRect.top
  tooltipTop.value = Math.max(
    TOOLTIP_MARGIN_PX,
    Math.min(viewportEl.value.clientHeight - TOOLTIP_MARGIN_PX, center),
  )
}

function showTooltip(index: number): void {
  hoveredIndex.value = index
  emit('hover', index)
  void nextTick(updateTooltipPosition)
}

function hideTooltip(): void {
  hoveredIndex.value = null
}

watch(
  () => props.virtualIndex,
  () => {
    if (hoveredIndex.value !== null) {
      window.requestAnimationFrame(updateTooltipPosition)
    }
  },
)
</script>

<template>
  <nav
    v-if="nodes.length > 1"
    class="scroll-node-chain"
    aria-label="消息节点导航"
  >
    <div class="node-spine" aria-hidden="true" />
    <div ref="viewportEl" class="node-viewport">
      <div class="node-track" :style="{ transform: trackTransform }">
        <button
          v-for="(node, index) in nodes"
          :key="node.id"
          :ref="(el) => setNodeElement(index, el)"
          class="node-button"
          :class="{ 'is-current': index === currentIndex }"
          :style="{ top: `${index * NODE_GAP_PX}px` }"
          :aria-label="node.label || `消息节点 ${index + 1}`"
          type="button"
          @click="emit('seek', index)"
          @mouseenter="showTooltip(index)"
          @focus="showTooltip(index)"
          @mouseleave="hideTooltip"
          @blur="hideTooltip"
        >
          <span class="node-line" />
        </button>
      </div>
    </div>
    <div
      class="node-tooltip"
      :class="{ 'is-visible': hoveredIndex !== null }"
      :style="{ top: `${tooltipTop}px` }"
      aria-hidden="true"
    >
      {{ tooltipLabel }}
    </div>
  </nav>
</template>

<style scoped>
.scroll-node-chain {
  position: absolute;
  top: 50%;
  right: 18px;
  z-index: 30;
  width: 236px;
  height: 304px;
  transform: translateY(-50%);
  pointer-events: none;
}

.node-spine {
  position: absolute;
  top: 0;
  right: 27px;
  bottom: 0;
  width: 1px;
  border-radius: 999px;
  background: rgb(31 41 55 / 0.025);
}

.node-viewport {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.node-track {
  position: absolute;
  top: 0;
  right: 0;
  width: 100%;
  will-change: transform;
}

.node-button {
  position: absolute;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 100%;
  height: 28px;
  transform: translateY(-50%);
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  color: inherit;
  font: inherit;
  pointer-events: auto;
  cursor: pointer;
}

.node-line {
  width: 13px;
  height: 3px;
  border-radius: 999px;
  background: #d1d5db;
  opacity: 0.9;
  transition:
    width 160ms cubic-bezier(0.2, 0.8, 0.2, 1),
    height 160ms cubic-bezier(0.2, 0.8, 0.2, 1),
    background-color 160ms cubic-bezier(0.2, 0.8, 0.2, 1),
    opacity 160ms cubic-bezier(0.2, 0.8, 0.2, 1),
    transform 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.node-button.is-current .node-line,
.node-button.is-current:hover .node-line,
.node-button.is-current:focus-visible .node-line {
  width: 15px;
  height: 4px;
  background: #4c1d95;
  opacity: 1;
}

.node-button:not(.is-current):hover .node-line,
.node-button:not(.is-current):focus-visible .node-line {
  width: 28px;
  height: 3px;
  background: #111827;
  opacity: 1;
  transform: translateX(-1px);
}

.node-button:focus-visible {
  outline: none;
}

.node-tooltip {
  position: absolute;
  top: 50%;
  right: 52px;
  max-width: 178px;
  transform: translateY(-50%) translateX(5px);
  overflow: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: rgb(255 255 255 / 0.94);
  padding: 5px 8px;
  color: #1f2937;
  font-size: 12px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0;
  box-shadow: 0 12px 28px rgb(17 24 39 / 0.1);
  backdrop-filter: blur(14px);
  pointer-events: none;
  transition:
    opacity 150ms cubic-bezier(0.2, 0.8, 0.2, 1),
    top 150ms cubic-bezier(0.2, 0.8, 0.2, 1),
    transform 150ms cubic-bezier(0.2, 0.8, 0.2, 1);
}

.node-tooltip::after {
  content: "";
  position: absolute;
  top: 50%;
  right: -12px;
  width: 12px;
  height: 1px;
  transform: translateY(-50%);
  background: #111827;
  opacity: 0.85;
}

.node-tooltip.is-visible {
  transform: translateY(-50%) translateX(0);
  opacity: 1;
}

@media (max-width: 760px) {
  .scroll-node-chain {
    right: 9px;
    width: 204px;
  }

  .node-tooltip {
    right: 46px;
    max-width: 154px;
  }
}
</style>
