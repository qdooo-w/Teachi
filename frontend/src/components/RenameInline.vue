<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'

interface Props {
  initial: string
  placeholder?: string
  maxLength?: number
  submitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '输入新名称',
  maxLength: 100,
  submitting: false,
})

const emit = defineEmits<{
  (e: 'submit', value: string): void
  (e: 'cancel'): void
}>()

const value = ref(props.initial)
const inputEl = ref<HTMLInputElement | null>(null)

onMounted(() => {
  nextTick(() => {
    inputEl.value?.focus()
    inputEl.value?.select()
  })
})

function handleSubmit(): void {
  const trimmed = value.value.trim()
  if (!trimmed || props.submitting) return
  if (trimmed === props.initial) {
    emit('cancel')
    return
  }
  emit('submit', trimmed)
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    event.preventDefault()
    handleSubmit()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
  }
}
</script>

<template>
  <div class="flex items-center gap-2" @click.stop>
    <input
      ref="inputEl"
      v-model="value"
      type="text"
      :maxlength="maxLength"
      :placeholder="placeholder"
      :disabled="submitting"
      class="h-9 flex-1 rounded-md border border-[#1f6f5b] bg-white px-3 text-sm text-[#1f2937] outline-none focus:ring-2 focus:ring-[#1f6f5b]/20"
      @keydown="handleKeydown"
    />
    <button
      type="button"
      class="h-9 rounded-md border border-[#d1d5db] bg-white px-3 text-sm text-[#4b5563] transition-colors hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="submitting"
      @click="emit('cancel')"
    >
      取消
    </button>
    <button
      type="button"
      class="h-9 rounded-md bg-[#1f2937] px-3 text-sm text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]"
      :disabled="submitting || !value.trim()"
      @click="handleSubmit"
    >
      {{ submitting ? '保存中' : '确认' }}
    </button>
  </div>
</template>
