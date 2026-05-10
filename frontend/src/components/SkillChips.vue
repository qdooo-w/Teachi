<script setup lang="ts">
import type { SkillMeta } from '../skills'

defineProps<{
  skills: SkillMeta[]
}>()

const emit = defineEmits<{
  remove: [name: string]
}>()
</script>

<template>
  <div class="flex flex-wrap gap-1.5 px-1 pb-1">
    <span
      v-for="skill in skills"
      :key="skill.name"
      class="flex items-center gap-1 rounded-full bg-[#e6f4ee] px-2.5 py-0.5 text-xs font-medium text-[#1f6f5b]"
    >
      {{ skill.name }}
      <button
        class="flex h-3.5 w-3.5 items-center justify-center rounded-full hover:bg-[#1f6f5b]/20"
        type="button"
        :aria-label="`移除 ${skill.name}`"
        @click="emit('remove', skill.name)"
      >
        <svg class="h-2.5 w-2.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </span>
  </div>
</template>
