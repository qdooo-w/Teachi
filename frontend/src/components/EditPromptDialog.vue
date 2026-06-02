<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch, computed } from 'vue'

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

const isDirty = computed(() => {
  return draft.value !== props.initialText && draft.value.trim() !== ''
})

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
  <Transition name="dialog-fade" appear>
    <div
      v-if="modelValue"
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm px-4"
      @click="close"
    >
      <div class="modal-card relative w-full max-w-[560px] rounded-2xl bg-white p-5 shadow-xl" @click.stop>
        <button
          type="button"
          class="absolute top-4 right-4 text-[#9ca3af] hover:text-[#6b7280] transition-colors"
          :disabled="submitting"
          @click="close"
        >
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <h3 class="mb-3 text-base font-semibold text-[#1f2937]">{{ title }}</h3>
        <textarea
          ref="textarea"
          v-model="draft"
          rows="6"
          class="block w-full resize-none rounded-lg bg-[#f3f4f6] px-3 py-2 text-sm leading-relaxed text-[#1f2937] outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20"
          :placeholder="placeholder"
          :disabled="submitting"
        />
        <p v-if="error" class="mt-3 rounded-lg bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
          {{ error }}
        </p>
        <div class="mt-4 flex items-center justify-between">
          <p class="text-xs text-[#9ca3af]">Ctrl/⌘ + Enter 提交，Esc 取消</p>
          <div class="flex items-center gap-2">
            <Transition name="fade">
              <button
                v-if="isDirty"
                type="button"
                class="h-9 rounded-lg bg-[#1f2937] px-4 text-sm text-white font-medium transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="submitting || !draft.trim()"
                @click="submit"
              >
                {{ submitting ? '处理中...' : '提交重放' }}
              </button>
            </Transition>
          </div>
        </div>
      </div>
    </div>
  </Transition>
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
