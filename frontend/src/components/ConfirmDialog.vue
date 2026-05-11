<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

interface Props {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
  submitting?: boolean
  error?: string
}

withDefaults(defineProps<Props>(), {
  confirmText: '确认',
  cancelText: '取消',
  danger: false,
  submitting: false,
  error: '',
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('cancel')
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 px-4" @click="emit('cancel')">
    <div class="w-full max-w-[420px] rounded-xl bg-white p-5 shadow-xl" @click.stop>
      <h3 class="mb-2 text-base font-semibold text-[#1f2937]">{{ title }}</h3>
      <p class="whitespace-pre-wrap text-sm text-[#4b5563]">{{ message }}</p>
      <p v-if="error" class="mt-3 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
        {{ error }}
      </p>
      <div class="mt-5 flex items-center justify-end gap-2">
        <button
          type="button"
          class="h-9 rounded-md border border-[#d1d5db] bg-white px-4 text-sm text-[#4b5563] transition-colors hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="submitting"
          @click="emit('cancel')"
        >
          {{ cancelText }}
        </button>
        <button
          type="button"
          :class="[
            'h-9 rounded-md px-4 text-sm text-white transition-colors disabled:cursor-not-allowed disabled:opacity-60',
            danger ? 'bg-[#b91c1c] hover:bg-[#991b1b]' : 'bg-[#1f2937] hover:bg-[#111827]',
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
