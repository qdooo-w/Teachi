<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { SkillMeta } from '../skills'

const props = defineProps<{
  skills: SkillMeta[]
  selected: string[]
}>()

const emit = defineEmits<{
  toggle: [name: string]
  close: []
}>()

const query = ref('')
const activeIndex = ref(0)
const listEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLInputElement | null>(null)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q
    ? props.skills.filter((s) =>
        s.name.includes(q)
        || (s.display_name ?? '').toLowerCase().includes(q)
        || s.description.toLowerCase().includes(q),
      )
    : props.skills
})

watch(filtered, () => { activeIndex.value = 0 })

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, filtered.value.length - 1)
    scrollActiveIntoView()
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
    scrollActiveIntoView()
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const skill = filtered.value[activeIndex.value]
    if (skill) emit('toggle', skill.name)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

function scrollActiveIntoView() {
  nextTick(() => {
    const el = listEl.value?.querySelector<HTMLElement>('[data-active="true"]')
    el?.scrollIntoView({ block: 'nearest' })
  })
}

// 自动聚焦搜索框，让键盘导航立刻可用
nextTick(() => { inputEl.value?.focus() })
</script>

<template>
  <!-- 抽屉：与 composer 同宽，顶部圆角、上边框、底部无圆角与 composer 无缝衔接 -->
  <div
    class="overflow-hidden rounded-t-3xl border-x border-t border-[#d1d5db] bg-[#e5e7eb]"
    @keydown="handleKeydown"
  >
    <div class="flex items-center justify-between border-b border-[#d1d5db]/70 px-4 py-2">
      <input
        ref="inputEl"
        v-model="query"
        class="h-7 flex-1 bg-transparent text-sm outline-none placeholder:text-[#9ca3af]"
        placeholder="搜索技能..."
        type="text"
      />
      <button
        class="ml-2 flex h-6 w-6 items-center justify-center rounded text-[#6b7280] hover:bg-white/60 hover:text-[#1f2937]"
        type="button"
        title="关闭 (Esc)"
        @click="emit('close')"
      >
        <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div ref="listEl" class="max-h-60 overflow-y-auto py-1">
      <div v-if="filtered.length === 0" class="px-4 py-3 text-sm text-[#9ca3af]">无匹配技能</div>
      <button
        v-for="(skill, i) in filtered"
        :key="skill.name"
        :data-active="i === activeIndex ? 'true' : undefined"
        :class="[
          'flex w-full items-center gap-2 px-4 py-2 text-left transition-colors',
          i === activeIndex ? 'bg-white/70' : 'hover:bg-white/50',
        ]"
        type="button"
        @click="emit('toggle', skill.name)"
        @mouseenter="activeIndex = i"
      >
        <span
          :class="[
            'flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border text-[10px]',
            selected.includes(skill.name)
              ? 'border-[#1f6f5b] bg-[#1f6f5b] text-white'
              : 'border-[#9ca3af] bg-white/70',
          ]"
        >
          <svg v-if="selected.includes(skill.name)" class="h-2.5 w-2.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
          </svg>
        </span>
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium text-[#1f2937]">{{ skill.display_name || skill.name }}</div>
          <div class="truncate text-xs text-[#6b7280]">{{ skill.description || '无描述' }}</div>
        </div>
      </button>
    </div>
  </div>
</template>
