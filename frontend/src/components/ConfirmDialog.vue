<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import type { ConfirmTone } from '../composables/useConfirmDialog'

interface Props {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  tone?: ConfirmTone
  danger?: boolean
  submitting?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  confirmText: '确认',
  cancelText: '取消',
  tone: 'default',
  danger: false,
  submitting: false,
  error: '',
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && !props.submitting) emit('cancel')
}

const effectiveTone = computed<ConfirmTone>(() => props.danger ? 'danger' : props.tone)
const iconClass = computed(() => {
  if (effectiveTone.value === 'danger') return 'bg-red-50 text-[#b91c1c]'
  if (effectiveTone.value === 'warning') return 'bg-amber-50 text-[#92400e]'
  return 'bg-slate-100 text-slate-700'
})
const confirmClass = computed(() => {
  if (effectiveTone.value === 'danger') return 'bg-[#b91c1c] hover:bg-[#991b1b]'
  return 'bg-[#1f2937] hover:bg-[#111827]'
})

onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div
    class="fixed inset-0 z-[1200] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
    @click="!submitting && emit('cancel')"
  >
    <div class="modal-card relative w-full max-w-[420px] rounded-2xl bg-white p-5 shadow-xl font-hans" @click.stop>
      <button
        type="button"
        class="absolute top-4 right-4 text-[#9ca3af] hover:text-[#6b7280] transition-colors"
        :disabled="submitting"
        @click="emit('cancel')"
      >
        <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      <div class="mb-3 flex items-start gap-3 pr-8">
        <div :class="['mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl', iconClass]">
          <svg v-if="effectiveTone === 'danger'" class="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v4m0 4h.01M5.07 19h13.86a2 2 0 0 0 1.73-3L13.73 4a2 2 0 0 0-3.46 0L3.34 16a2 2 0 0 0 1.73 3Z" />
          </svg>
          <svg v-else-if="effectiveTone === 'warning'" class="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v5m0 3h.01M12 3 2.7 19h18.6L12 3Z" />
          </svg>
          <svg v-else class="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h8m-8 4h5M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
          </svg>
        </div>
        <div class="min-w-0">
          <h3 class="mb-1 text-base font-semibold text-[#1f2937]">{{ title }}</h3>
          <p class="whitespace-pre-wrap text-sm leading-6 text-[#4b5563]">{{ message }}</p>
        </div>
      </div>
      <p v-if="error" class="mt-3 rounded-lg bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
        {{ error }}
      </p>
      <div class="mt-5 flex items-center justify-end gap-2">
        <button
          type="button"
          class="h-9 rounded-lg border border-[#d1d5db] bg-white px-4 text-sm font-medium text-[#4b5563] transition-colors hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="submitting"
          @click="emit('cancel')"
        >
          {{ cancelText }}
        </button>
        <button
          type="button"
          :class="[
            'h-9 rounded-lg px-4 text-sm text-white font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60',
            confirmClass,
          ]"
          :disabled="submitting"
          @click="emit('confirm')"
        >
          {{ submitting ? '处理中...' : confirmText }}
        </button>
      </div>
    </div>
  </div>
</template>
