<script setup lang="ts">
import { ref, computed } from 'vue'
import { uploadLibrarySkillZip, getErrorMessage } from '../api'
import { confirmWarning } from '../composables/useConfirmDialog'

const emit = defineEmits<{
  close: []
  done: []
}>()

const MAX_UPLOAD_BYTES = 40 * 1024 * 1024 // 40MB

interface QueueItem {
  id: string
  file: File
  status: 'pending' | 'uploading' | 'success' | 'error'
  error?: string
}

const uploadQueue = ref<QueueItem[]>([])
const isBatchUploading = ref(false)
const isDragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const queueStats = computed(() => {
  const total = uploadQueue.value.length
  const success = uploadQueue.value.filter((i) => i.status === 'success').length
  const error = uploadQueue.value.filter((i) => i.status === 'error').length
  const uploading = uploadQueue.value.filter((i) => i.status === 'uploading').length
  const pending = uploadQueue.value.filter((i) => i.status === 'pending').length
  const done = success + error
  const progressPercent = total > 0 ? Math.round((done / total) * 100) : 0
  return { total, success, error, uploading, pending, progressPercent }
})

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function openFilePicker(): void {
  fileInputRef.value?.click()
}

function addFiles(files: FileList | null): void {
  if (!files) return
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (uploadQueue.value.some((item) => item.file.name === file.name && item.file.size === file.size)) {
      continue
    }
    let status: 'pending' | 'error' = 'pending'
    let error: string | undefined

    if (!file.name.toLowerCase().endsWith('.zip')) {
      status = 'error'
      error = '只允许上传 zip 文件'
    } else if (file.size > MAX_UPLOAD_BYTES) {
      status = 'error'
      error = '文件大小不能超过 40MB'
    }

    uploadQueue.value.push({
      id: Math.random().toString(36).substring(2, 9),
      file,
      status,
      error,
    })
  }
}

function handleFileInput(e: Event): void {
  const input = e.target as HTMLInputElement
  addFiles(input.files)
  input.value = ''
}

async function startBatchUpload(): Promise<void> {
  if (isBatchUploading.value) return
  const pendingItems = uploadQueue.value.filter((i) => i.status === 'pending')
  if (pendingItems.length === 0) return

  isBatchUploading.value = true
  for (const item of uploadQueue.value) {
    if (item.status !== 'pending') continue
    item.status = 'uploading'
    try {
      await uploadLibrarySkillZip(item.file)
      item.status = 'success'
    } catch (e) {
      item.status = 'error'
      item.error = getErrorMessage(e)
    }
  }
  isBatchUploading.value = false
}

function removeItem(id: string): void {
  if (isBatchUploading.value) return
  uploadQueue.value = uploadQueue.value.filter((i) => i.id !== id)
}

function clearQueue(): void {
  if (isBatchUploading.value) return
  uploadQueue.value = []
}

async function close(): Promise<void> {
  if (isBatchUploading.value) {
    const confirmed = await confirmWarning({
      title: '上传仍在进行',
      message: '正在上传中，确定要关闭吗？',
      confirmText: '关闭',
    })
    if (!confirmed) return
  }
  const hasFinished = uploadQueue.value.some((i) => i.status === 'success')
  uploadQueue.value = []
  emit('close')
  if (hasFinished) emit('done')
}

function handleDragOver(e: DragEvent): void {
  e.preventDefault()
  if (isBatchUploading.value) return
  isDragOver.value = true
}

function handleDragLeave(e: DragEvent): void {
  e.preventDefault()
  isDragOver.value = false
}

function handleDrop(e: DragEvent): void {
  e.preventDefault()
  isDragOver.value = false
  if (isBatchUploading.value) return
  if (e.dataTransfer?.files) {
    addFiles(e.dataTransfer.files)
  }
}
</script>

<template>
  <Transition name="dialog-fade" appear>
    <div
      class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 backdrop-blur-sm"
      @click.self="close"
    >
      <div class="modal-card font-hans flex h-[520px] w-[600px] max-w-[95vw] flex-col rounded-2xl bg-white shadow-xl overflow-hidden">
        <!-- 头部 -->
        <div class="flex h-14 flex-shrink-0 items-center justify-between px-5 bg-slate-50/50 border-b border-slate-100">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-slate-700 text-sm">上传技能 ZIP</span>
            <span
              v-if="queueStats.total > 0"
              class="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600"
            >
              已选 {{ queueStats.total }}
            </span>
          </div>
          <button
            class="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-all duration-200 active:scale-90"
            type="button"
            @click="close"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- 主体 -->
        <div class="min-h-0 flex-1 overflow-y-auto p-5 flex flex-col gap-4">
          <input
            ref="fileInputRef"
            type="file"
            accept=".zip"
            multiple
            class="hidden"
            @change="handleFileInput"
          />

          <!-- 拖放区域 -->
          <div
            :class="[
              'flex flex-col items-center justify-center rounded-2xl p-8 text-center cursor-pointer transition-all duration-300',
              isDragOver
                ? 'bg-slate-100/90 scale-[0.98]'
                : 'bg-slate-50/80 hover:bg-slate-100/60 hover:scale-[0.99]'
            ]"
            @dragover="handleDragOver"
            @dragleave="handleDragLeave"
            @drop="handleDrop"
            @click="openFilePicker"
          >
            <div class="flex flex-col items-center gap-2">
              <div
                class="p-3 bg-white rounded-full shadow-sm text-slate-400 transition-transform duration-300"
                :class="isDragOver ? 'scale-110 text-slate-600' : ''"
              >
                <svg class="w-8 h-8" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <div>
                <span class="text-sm font-medium text-slate-700">点击选择</span>
                <span class="text-sm text-slate-500"> 或拖入 ZIP 文件到这里</span>
              </div>
              <span class="text-xs text-slate-400">支持批量上传，每个文件不超过 40MB</span>
            </div>
          </div>

          <!-- 进度条 -->
          <div
            v-if="queueStats.total > 0 && (isBatchUploading || queueStats.success > 0 || queueStats.error > 0)"
            class="bg-slate-50/80 rounded-2xl p-4 flex flex-col gap-2.5"
          >
            <div class="flex items-center justify-between text-xs text-slate-500 font-medium">
              <span>上传进度：{{ queueStats.success + queueStats.error }} / {{ queueStats.total }}</span>
              <span>{{ queueStats.progressPercent }}%</span>
            </div>
            <div class="h-1.5 w-full bg-slate-200/80 rounded-full overflow-hidden">
              <div
                class="h-full bg-slate-800 rounded-full transition-all duration-300 ease-out"
                :style="{ width: `${queueStats.progressPercent}%` }"
              />
            </div>
            <div class="flex gap-4 text-[10px] font-medium">
              <span class="text-emerald-600">成功：{{ queueStats.success }}</span>
              <span class="text-rose-500">失败：{{ queueStats.error }}</span>
              <span v-if="queueStats.uploading > 0" class="text-slate-700 animate-pulse">正在上传...</span>
            </div>
          </div>

          <!-- 文件队列 -->
          <div v-if="uploadQueue.length > 0" class="flex-1 min-h-0 flex flex-col gap-2">
            <div class="flex justify-between items-center text-xs text-slate-500 font-medium">
              <span>文件列表</span>
              <button
                class="text-rose-500 hover:text-rose-600 hover:bg-rose-50/50 active:bg-rose-100/50 px-2 py-1 rounded-lg transition-all disabled:opacity-50 text-[11px] font-medium"
                :disabled="isBatchUploading"
                type="button"
                @click="clearQueue"
              >
                清空队列
              </button>
            </div>
            <div class="flex-1 min-h-0 overflow-y-auto rounded-2xl bg-slate-50/40 p-2 space-y-1.5">
              <div
                v-for="item in uploadQueue"
                :key="item.id"
                :class="[
                  'flex items-center justify-between py-2.5 px-3 text-xs gap-3 rounded-xl transition-all duration-200',
                  item.status === 'success' ? 'bg-emerald-50/40 text-emerald-800' :
                  item.status === 'error' ? 'bg-rose-50/40 text-rose-800' :
                  item.status === 'uploading' ? 'bg-amber-50/60 text-amber-800' :
                  'bg-white hover:bg-slate-50/80 text-slate-700'
                ]"
              >
                <div class="flex items-center gap-2 min-w-0 flex-1">
                  <div class="flex-shrink-0">
                    <svg v-if="item.status === 'pending'" class="w-4 h-4 text-slate-400" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <svg v-else-if="item.status === 'uploading'" class="w-4 h-4 text-amber-500 animate-spin" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89" />
                    </svg>
                    <svg v-else-if="item.status === 'success'" class="w-4 h-4 text-emerald-500" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                    <svg v-else-if="item.status === 'error'" class="w-4 h-4 text-rose-500" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                  <span
                    class="truncate font-medium min-w-0"
                    :title="item.file.name"
                  >{{ item.file.name }}</span>
                  <span class="text-[10px] flex-shrink-0 tabular-nums text-slate-400">{{ formatBytes(item.file.size) }}</span>
                </div>

                <div class="flex items-center gap-2 flex-shrink-0">
                  <span v-if="item.status === 'error'" class="text-[10px] text-rose-500 truncate max-w-[120px]" :title="item.error">
                    {{ item.error }}
                  </span>
                  <button
                    v-if="item.status !== 'uploading'"
                    class="flex-shrink-0 rounded-full p-1 text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-colors"
                    type="button"
                    @click="removeItem(item.id)"
                  >
                    <svg class="w-3.5 h-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部 -->
        <div class="flex-shrink-0 bg-slate-50/80 px-5 py-3.5 border-t border-slate-100 flex items-center justify-between">
          <span class="text-xs text-slate-400">
            {{ queueStats.total > 0 ? `共 ${queueStats.total} 个文件` : '选择 ZIP 文件开始上传' }}
          </span>
          <button
            class="h-9 rounded-xl bg-slate-900 px-4 text-sm text-white font-semibold transition-all duration-200 hover:bg-slate-800 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100"
            :disabled="isBatchUploading || queueStats.pending === 0"
            type="button"
            @click="startBatchUpload"
          >
            {{ isBatchUploading ? '上传中...' : `开始上传${queueStats.pending > 0 ? ` (${queueStats.pending})` : ''}` }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>
