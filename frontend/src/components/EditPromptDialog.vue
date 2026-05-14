<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

interface Props {
  modelValue: boolean
  initialText: string
  title?: string
  placeholder?: string
  submitting?: boolean
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '编辑提示词',
  placeholder: '输入新的提示词...',
  submitting: false,
  error: '',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'submit', text: string): void
}>()

const draft = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

watch(
  () => props.modelValue,
  async (open) => {
    if (open) {
      draft.value = props.initialText
      await nextTick()
      textarea.value?.focus()
      textarea.value?.select()
    }
  },
  { immediate: true },
)

function close(): void {
  if (props.submitting) return
  emit('update:modelValue', false)
}

function submit(): void {
  const text = draft.value.trim()
  if (!text) return
  emit('submit', text)
}

function handleKeydown(event: KeyboardEvent): void {
  if (!props.modelValue) return
  if (event.key === 'Escape') {
    close()
    return
  }
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    submit()
  }
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div
    v-if="modelValue"
    class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 px-4"
    @click="close"
  >
    <div class="w-full max-w-[560px] rounded-xl bg-white p-5 shadow-xl" @click.stop>
      <h3 class="mb-3 text-base font-semibold text-[#1f2937]">{{ title }}</h3>
      <textarea
        ref="textarea"
        v-model="draft"
        rows="6"
        class="block w-full resize-none rounded-md border border-[#d1d5db] bg-white px-3 py-2 text-sm leading-relaxed text-[#1f2937] outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
        :placeholder="placeholder"
        :disabled="submitting"
      />
      <p v-if="error" class="mt-3 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
        {{ error }}
      </p>
      <div class="mt-4 flex items-center justify-between">
        <p class="text-xs text-[#9ca3af]">Ctrl/⌘ + Enter 提交，Esc 取消</p>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="h-9 rounded-md border border-[#d1d5db] bg-white px-4 text-sm text-[#4b5563] transition-colors hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="submitting"
            @click="close"
          >
            取消
          </button>
          <button
            type="button"
            class="h-9 rounded-md bg-[#1f2937] px-4 text-sm text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="submitting || !draft.trim()"
            @click="submit"
          >
            {{ submitting ? '处理中...' : '提交重放' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
