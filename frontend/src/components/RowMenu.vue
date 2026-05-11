<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

interface Props {
  open: boolean
  disableDelete?: boolean
  deleteDisabledReason?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'close'): void
  (e: 'rename'): void
  (e: 'delete'): void
}>()

const rootEl = ref<HTMLElement | null>(null)

// 外部点击 / Esc 关闭；在 mousedown 捕获阶段处理，保证其他菜单按钮的 click 仍能打开新菜单
function handleMousedown(event: MouseEvent): void {
  if (!props.open) return
  if (rootEl.value && !rootEl.value.contains(event.target as Node)) {
    emit('close')
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (props.open && event.key === 'Escape') emit('close')
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      document.addEventListener('mousedown', handleMousedown, true)
      document.addEventListener('keydown', handleKeydown)
    } else {
      document.removeEventListener('mousedown', handleMousedown, true)
      document.removeEventListener('keydown', handleKeydown)
    }
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleMousedown, true)
  document.removeEventListener('keydown', handleKeydown)
})

function pickRename(): void {
  emit('close')
  emit('rename')
}

function pickDelete(): void {
  if (props.disableDelete) return
  emit('close')
  emit('delete')
}
</script>

<template>
  <div ref="rootEl" class="relative">
    <button
      type="button"
      class="flex h-7 w-7 items-center justify-center rounded-md text-[#9ca3af] transition-colors hover:bg-[#e5e7eb] hover:text-[#4b5563]"
      title="更多操作"
      @click.stop="emit('toggle')"
    >
      <svg class="h-4 w-4" aria-hidden="true" fill="currentColor" viewBox="0 0 24 24">
        <circle cx="5" cy="12" r="1.6" />
        <circle cx="12" cy="12" r="1.6" />
        <circle cx="19" cy="12" r="1.6" />
      </svg>
    </button>

    <div
      v-if="open"
      class="absolute right-0 top-full z-30 mt-1 min-w-[140px] overflow-hidden rounded-lg border border-[#d1d5db] bg-white py-1 shadow-lg"
      @click.stop
    >
      <button
        type="button"
        class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-[#1f2937] transition-colors hover:bg-[#f3f4f6]"
        @click="pickRename"
      >
        <svg class="h-4 w-4 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
        重命名
      </button>
      <button
        type="button"
        :class="[
          'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
          disableDelete
            ? 'cursor-not-allowed text-[#9ca3af]'
            : 'text-[#b91c1c] hover:bg-[#fef2f2]',
        ]"
        :title="disableDelete ? deleteDisabledReason : ''"
        :disabled="disableDelete"
        @click="pickDelete"
      >
        <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3" />
        </svg>
        删除
      </button>
    </div>
  </div>
</template>
