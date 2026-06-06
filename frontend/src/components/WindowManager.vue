<script setup lang="ts">
interface PreviewItem {
  id: string
  type: 'image' | 'mermaid' | 'math' | 'table'
  source: string
  index: number
  windowX?: number
  windowY?: number
  windowWidth?: number
  windowHeight?: number
  minimized?: boolean
}

const props = defineProps<{
  previews: PreviewItem[]
}>()

const emit = defineEmits<{
  (e: 'close-preview', id: string): void
  (e: 'close-all'): void
  (e: 'focus-preview', id: string): void
  (e: 'toggle-minimize', id: string): void
  (e: 'close'): void
}>()

// Helper to extract a display title for each preview item
function getPreviewTitle(item: PreviewItem): string {
  if (item.type === 'image') {
    return '图片预览'
  } else if (item.type === 'mermaid') {
    return 'Mermaid 架构图'
  } else if (item.type === 'math') {
    return 'LaTeX 数学公式'
  } else {
    return '数据表格预览'
  }
}

// Helper to extract a short description/filename
function getPreviewDesc(item: PreviewItem): string {
  const src = item.source
  if (item.type === 'image') {
    if (src.startsWith('blob:') || src.startsWith('data:')) {
      return '临时生成图'
    }
    // Extract filename from URL
    try {
      const urlPart = src.split('?')[0]
      return urlPart.substring(urlPart.lastIndexOf('/') + 1) || '远程图片'
    } catch {
      return '网络图片'
    }
  } else if (item.type === 'mermaid') {
    // Extract first non-empty line of Mermaid source code
    const lines = src.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length > 0) {
      // Return first line, truncated
      return lines[0].length > 40 ? lines[0].substring(0, 40) + '...' : lines[0]
    }
    return 'Mermaid 图表代码'
  } else if (item.type === 'math') {
    // Show LaTeX snippet
    return src.length > 40 ? src.substring(0, 40) + '...' : src
  } else {
    // Strip HTML tags for clean text preview
    const cleanText = src.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
    return cleanText.length > 45 ? cleanText.substring(0, 45) + '...' : cleanText || '表格数据'
  }
}
</script>

<template>
  <!-- Window Manager Drawer: matches SkillPicker styles -->
  <div class="overflow-hidden rounded-t-3xl border-x border-t border-[#d1d5db] bg-[#e5e7eb]">
    <!-- Header -->
    <div class="flex items-center justify-between border-b border-[#d1d5db]/70 px-4 py-1.5">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-[#4b5563]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <rect x="3" y="3" width="18" height="18" rx="2" stroke-width="2" />
          <line x1="3" y1="9" x2="21" y2="9" stroke-width="2" />
        </svg>
        <span class="text-xs font-semibold text-[#374151]">
          窗口管理 ({{ previews.length }}/8)
        </span>
      </div>

      <div class="flex items-center gap-2">
        <!-- Close All Button -->
        <button
          v-if="previews.length > 0"
          class="px-2 py-0.5 bg-transparent hover:bg-transparent text-neutral-400 hover:text-red-500 font-medium transition-colors border-0 cursor-pointer flex items-center justify-center"
          type="button"
          @click="emit('close-all')"
        >
          <span style="display: inline-block; font-size: 12px; transform: scale(0.85); transform-origin: right center; white-space: nowrap;">
            一键关闭
          </span>
        </button>
        <!-- Close Drawer -->
        <button
          class="flex h-6 w-6 items-center justify-center rounded text-[#6b7280] hover:bg-white/60 hover:text-[#1f2937] cursor-pointer"
          type="button"
          title="关闭"
          @click="emit('close')"
        >
          <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Active Windows List -->
    <div class="max-h-60 overflow-y-auto py-1">
      <div v-if="previews.length === 0" class="px-4 py-8 text-center text-xs text-[#9ca3af]">
        当前没有打开的预览窗口
      </div>

      <div
        v-for="preview in previews"
        :key="preview.id"
        class="flex items-center justify-between px-4 py-1 hover:bg-white/50 transition-colors border-b border-[#d1d5db]/30 last:border-b-0 cursor-pointer group"
        :class="{ 'opacity-65 bg-neutral-50/30': preview.minimized }"
        @click="emit('focus-preview', preview.id)"
      >
        <div class="flex items-center gap-3 min-w-0 flex-1">
          <!-- Window Number Badge -->
          <div class="h-6 w-6 rounded-none bg-neutral-300 text-neutral-800 font-bold text-[10px] flex items-center justify-center flex-shrink-0 select-none">
            #{{ preview.index }}
          </div>

          <!-- Description -->
          <div class="min-w-0 flex-1 flex flex-col justify-center gap-0.5">
            <div class="flex items-center gap-1.5 leading-none">
              <span class="text-xs font-semibold text-[#1f2937] truncate">
                {{ getPreviewTitle(preview) }}
              </span>
              <span class="text-[9px] px-1 bg-neutral-200 text-neutral-600 rounded">
                {{ preview.type }}
              </span>
              <span v-if="preview.minimized" class="text-[9px] px-1 bg-amber-100 text-amber-700 rounded border border-amber-200 font-medium">
                已挂起
              </span>
            </div>
            <div class="text-[10px] text-[#6b7280] truncate leading-none">
              {{ getPreviewDesc(preview) }}
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex items-center gap-1" @click.stop>
          <!-- Minimize / Restore Button -->
          <button
            class="p-1 hover:bg-neutral-100 hover:text-neutral-700 text-neutral-400 rounded transition-colors border-0 cursor-pointer flex items-center justify-center"
            :title="preview.minimized ? '还原窗口' : '挂起窗口'"
            type="button"
            @click="emit('toggle-minimize', preview.id)"
          >
            <svg v-if="!preview.minimized" class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4" />
            </svg>
            <svg v-else class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
            </svg>
          </button>
          <!-- Close Button -->
          <button
            class="p-1 hover:bg-red-50 hover:text-red-600 text-neutral-400 rounded transition-colors border-0 cursor-pointer flex items-center justify-center"
            title="关闭窗口"
            type="button"
            @click="emit('close-preview', preview.id)"
          >
            <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
