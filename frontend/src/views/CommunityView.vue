<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  type CommunitySkillSummary,
  type CommunitySkillDetail,
  type CommunitySort,
  listCommunitySkills,
  getCommunitySkill,
  installCommunitySkill,
  deleteCommunitySkill,
  uploadCommunitySkillZip,
  getCurrentUserId,
  getErrorMessage,
} from '../api'
import { COMMUNITY_MAX_UPLOAD_BYTES, COMMUNITY_PAGE_LIMIT } from '../config'
import { useProjects } from '../composables/useProjects'

const { projects, loadProjects } = useProjects()

const currentUserId = ref<string | null>(getCurrentUserId())

const skills = ref<CommunitySkillSummary[]>([])
const total = ref(0)
const loading = ref(false)
const errorMsg = ref('')

import { useCommunity } from '../composables/useCommunity'

const { searchQuery: keyword, triggerSearch, showUploadModal } = useCommunity()
const sort = ref<CommunitySort>('popular')
const limit = COMMUNITY_PAGE_LIMIT
const offset = ref(0)

const selected = ref<CommunitySkillDetail | null>(null)
const detailLoading = ref(false)
const installing = ref(false)
const installingProject = ref(false)
const selectedProjectId = ref('')
const deleting = ref(false)
const flashMsg = ref('')
const uploadInput = ref<HTMLInputElement | null>(null)
const uploadMsg = ref('')
const uploadMsgKind = ref<'success' | 'error'>('success')

// 批量上传相关
interface UploadQueueItem {
  id: string
  file: File
  status: 'pending' | 'uploading' | 'success' | 'error'
  error?: string
}

// showUploadModal is imported from useCommunity
const uploadQueue = ref<UploadQueueItem[]>([])
const isDragOver = ref(false)
const isBatchUploading = ref(false)

const MAX_UPLOAD_ZIP_BYTES = COMMUNITY_MAX_UPLOAD_BYTES

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const currentPage = computed(() => Math.floor(offset.value / limit) + 1)
const isAuthor = computed(() => selected.value?.owner_uuid === currentUserId.value)

const queueStats = computed(() => {
  const total = uploadQueue.value.length
  const success = uploadQueue.value.filter((item) => item.status === 'success').length
  const error = uploadQueue.value.filter((item) => item.status === 'error').length
  const uploading = uploadQueue.value.filter((item) => item.status === 'uploading').length
  const pending = uploadQueue.value.filter((item) => item.status === 'pending').length
  const progressPercent = total > 0 ? Math.round(((success + error) / total) * 100) : 0
  return { total, success, error, uploading, pending, progressPercent }
})

function skillTitle(skill: { name: string; display_name?: string | null }): string {
  return skill.display_name || skill.name
}

async function load(): Promise<void> {
  loading.value = true
  errorMsg.value = ''
  try {
    const r = await listCommunitySkills({
      keyword: keyword.value.trim() || undefined,
      limit,
      offset: offset.value,
      sort: sort.value,
    })
    skills.value = r.skills
    total.value = r.total
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function openDetail(id: string): Promise<void> {
  detailLoading.value = true
  errorMsg.value = ''
  try {
    selected.value = await getCommunitySkill(id)
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    detailLoading.value = false
  }
}

function closeDetail(): void {
  selected.value = null
  flashMsg.value = ''
}

async function doInstall(): Promise<void> {
  if (!selected.value) return
  installing.value = true
  flashMsg.value = ''
  try {
    const r = await installCommunitySkill(selected.value.id)
    selected.value.downloads = r.downloads
    const inList = skills.value.find((s) => s.id === selected.value!.id)
    if (inList) inList.downloads = r.downloads
    flashMsg.value = `已安装到我的技能：${r.name}`
  } catch (e) {
    flashMsg.value = getErrorMessage(e)
  } finally {
    installing.value = false
  }
}

async function doInstallProject(): Promise<void> {
  if (!selected.value || !selectedProjectId.value) return
  installingProject.value = true
  flashMsg.value = ''
  try {
    const r = await installCommunitySkill(selected.value.id, { target: 'project', pid: selectedProjectId.value })
    selected.value.downloads = r.downloads
    const inList = skills.value.find((s) => s.id === selected.value!.id)
    if (inList) inList.downloads = r.downloads
    const project = projects.value.find((p) => p.pid === selectedProjectId.value)
    flashMsg.value = `已安装到项目 ${project?.projectname ?? selectedProjectId.value}：${r.name}`
  } catch (e) {
    flashMsg.value = getErrorMessage(e)
  } finally {
    installingProject.value = false
  }
}

async function doDelete(): Promise<void> {
  if (!selected.value) return
  if (!confirm(`确定要删除社区中的 "${skillTitle(selected.value)}" 吗？此操作不可撤销。`)) return
  deleting.value = true
  try {
    await deleteCommunitySkill(selected.value.id)
    closeDetail()
    await load()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    deleting.value = false
  }
}

function openUploadPicker(): void {
  uploadInput.value?.click()
}

function addFilesToQueue(files: FileList | null): void {
  if (!files) return
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (uploadQueue.value.some((item) => item.file.name === file.name && item.file.size === file.size)) {
      continue
    }
    let status: 'pending' | 'error' = 'pending'
    let error: string | undefined = undefined

    if (!file.name.toLowerCase().endsWith('.zip')) {
      status = 'error'
      error = '只允许上传 zip 文件'
    } else if (file.size > MAX_UPLOAD_ZIP_BYTES) {
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

function handleZipUpload(event: Event): void {
  const input = event.target as HTMLInputElement
  if (input.files) {
    addFilesToQueue(input.files)
  }
  input.value = ''
}

async function startBatchUpload(): Promise<void> {
  if (isBatchUploading.value) return
  const pendingItems = uploadQueue.value.filter((item) => item.status === 'pending')
  if (pendingItems.length === 0) return

  isBatchUploading.value = true
  for (const item of uploadQueue.value) {
    if (item.status !== 'pending') continue
    item.status = 'uploading'
    try {
      await uploadCommunitySkillZip(item.file)
      item.status = 'success'
    } catch (e) {
      item.status = 'error'
      item.error = getErrorMessage(e)
    }
  }
  isBatchUploading.value = false
}

function removeQueueItem(id: string): void {
  if (isBatchUploading.value) return
  uploadQueue.value = uploadQueue.value.filter((item) => item.id !== id)
}

function clearQueue(): void {
  if (isBatchUploading.value) return
  uploadQueue.value = []
}

function closeUploadModal(): void {
  if (isBatchUploading.value) {
    if (!confirm('正在上传中，确定要关闭弹窗吗？未完成的上传任务将被取消。')) return
  }
  showUploadModal.value = false
  uploadQueue.value = []
  void load()
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
    addFilesToQueue(e.dataTransfer.files)
  }
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('zh-CN')
}

function changeSort(next: CommunitySort): void {
  if (sort.value === next) return
  sort.value = next
  offset.value = 0
  void load()
}

function submitSearch(): void {
  offset.value = 0
  void load()
}

function gotoPage(page: number): void {
  const p = Math.max(1, Math.min(totalPages.value, page))
  offset.value = (p - 1) * limit
  void load()
}

watch(triggerSearch, () => {
  submitSearch()
})

onMounted(() => {
  document.title = '社区 · Teachi'
  void load()
  void loadProjects()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-transparent">
    <!-- 搜索及上传控制栏 -->
    <div class="relative flex h-14 flex-shrink-0 items-center justify-between px-6 bg-transparent">
      <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-3">
        <input
          ref="uploadInput"
          class="hidden"
          accept=".zip,application/zip,application/x-zip-compressed"
          type="file"
          multiple
          @change="handleZipUpload"
        />
        <!-- 上传 ZIP 圆形按钮 -->
        <button
          class="flex h-9 w-9 items-center justify-center rounded-full hover:bg-[#e5e7eb] text-[#4b5563] transition-colors"
          type="button"
          title="上传 ZIP"
          @click="showUploadModal = true"
        >
          <svg class="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        </button>

        <!-- 居中搜索框 -->
        <div class="relative flex items-center bg-[#e5e7eb]/70 hover:bg-[#e5e7eb] focus-within:bg-white focus-within:ring-2 focus-within:ring-[#9ca3af]/20 transition-all rounded-2xl w-64 h-9">
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <svg class="h-4 w-4 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <input
            v-model="keyword"
            class="block w-full rounded-2xl bg-transparent py-1.5 pl-9 pr-3 text-sm text-[#1f2937] placeholder:text-[#9ca3af] outline-none"
            placeholder="搜索技能名或描述"
            type="search"
            @keyup.enter="submitSearch"
          />
        </div>
      </div>
    </div>

    <!-- 排序选项卡 -->
    <div class="flex flex-shrink-0 items-center justify-between bg-transparent px-6 py-2 text-sm">
      <div class="flex items-center gap-6">
        <button
          type="button"
          class="relative pb-2 text-sm font-medium transition-colors duration-200"
          :class="sort === 'popular' ? 'text-[#1f2937] font-semibold' : 'text-[#6b7280] hover:text-[#1f2937]'"
          @click="changeSort('popular')"
        >
          热门
          <span
            v-if="sort === 'popular'"
            class="absolute bottom-0 left-0 right-0 h-[2px] bg-[#1f2937] rounded-full"
          />
        </button>
        <button
          type="button"
          class="relative pb-2 text-sm font-medium transition-colors duration-200"
          :class="sort === 'newest' ? 'text-[#1f2937] font-semibold' : 'text-[#6b7280] hover:text-[#1f2937]'"
          @click="changeSort('newest')"
        >
          最新
          <span
            v-if="sort === 'newest'"
            class="absolute bottom-0 left-0 right-0 h-[2px] bg-[#1f2937] rounded-full"
          />
        </button>
      </div>
      <span class="text-xs text-[#4b5563]">共 {{ total }} 个技能</span>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <p
        v-if="errorMsg"
        class="mb-4 rounded-lg border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]"
      >
        {{ errorMsg }}
      </p>
      <p
        v-if="uploadMsg"
        :class="[
          'mb-4 rounded-lg border px-3 py-2 text-sm',
          uploadMsgKind === 'success'
            ? 'border-[#bbf7d0] bg-[#f0fdf4] text-[#166534]'
            : 'border-[#efb3a7] bg-[#fff7ed] text-[#9a3412]',
        ]"
      >
        {{ uploadMsg }}
      </p>

      <div v-if="loading" class="py-16 text-center text-sm text-[#9ca3af]">加载中...</div>
      <div v-else-if="skills.length === 0" class="py-16 text-center text-sm text-[#9ca3af]">
        还没有技能，去技能管理页发布第一个吧。
      </div>

      <div v-else class="flex flex-wrap gap-4">
        <button
          v-for="s in skills"
          :key="s.id"
          class="flex w-[280px] flex-col gap-2 rounded-2xl bg-white p-4 text-left shadow-sm transition hover:bg-[#f9fafb] hover:shadow-md"
          type="button"
          @click="openDetail(s.id)"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="truncate text-sm font-semibold text-[#1f2937]">{{ skillTitle(s) }}</span>
            <span class="flex flex-shrink-0 items-center gap-1 rounded-full bg-[#f3f4f6] px-2 py-0.5 text-[10px] tabular-nums text-[#6b7280]">
              <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m-7-7l7 7 7-7" />
              </svg>
              {{ s.downloads }}
            </span>
          </div>
          <p class="line-clamp-3 text-xs text-[#6b7280]">{{ s.description || '无描述' }}</p>
          <div class="mt-auto flex items-center justify-between text-[10px] text-[#9ca3af]">
            <span>{{ formatBytes(s.size_bytes) }}</span>
            <span>{{ formatDate(s.created_at) }}</span>
          </div>
        </button>
      </div>

      <div v-if="totalPages > 1" class="mt-5 flex items-center justify-center gap-2 text-sm">
        <button
          class="rounded-lg border border-[#e5e7eb] px-3 py-1 text-xs text-[#6b7280] disabled:opacity-50 hover:bg-[#f3f4f6]"
          :disabled="currentPage === 1"
          type="button"
          @click="gotoPage(currentPage - 1)"
        >
          上一页
        </button>
        <span class="text-xs tabular-nums text-[#9ca3af]">{{ currentPage }} / {{ totalPages }}</span>
        <button
          class="rounded-lg border border-[#e5e7eb] px-3 py-1 text-xs text-[#6b7280] disabled:opacity-50 hover:bg-[#f3f4f6]"
          :disabled="currentPage === totalPages"
          type="button"
          @click="gotoPage(currentPage + 1)"
        >
          下一页
        </button>
      </div>
    </div>

    <div
      v-if="selected || detailLoading"
      class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40"
      @click.self="closeDetail"
    >
      <div class="flex h-[640px] w-[760px] max-w-[95vw] flex-col rounded-xl bg-white shadow-xl">
        <div class="flex h-14 flex-shrink-0 items-center justify-between border-b border-[#e5e7eb] px-5">
          <div class="flex items-center gap-3">
            <span class="font-semibold text-[#1f2937]">{{ selected ? skillTitle(selected) : '加载中...' }}</span>
            <span
              v-if="selected"
              class="flex items-center gap-1 rounded-full bg-[#f3f4f6] px-2 py-0.5 text-[10px] tabular-nums text-[#6b7280]"
            >
              ⬇ {{ selected.downloads }}
            </span>
          </div>
          <button
            class="flex h-8 w-8 items-center justify-center rounded-lg text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#1f2937]"
            type="button"
            @click="closeDetail"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div v-if="!selected" class="flex flex-1 items-center justify-center text-sm text-[#9ca3af]">
          加载中...
        </div>
        <template v-else>
          <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <div class="mb-4 grid grid-cols-2 gap-4 text-xs text-[#6b7280]">
              <div><span class="text-[#9ca3af]">标识：</span>{{ selected.name }}</div>
              <div><span class="text-[#9ca3af]">大小：</span>{{ formatBytes(selected.size_bytes) }}</div>
              <div><span class="text-[#9ca3af]">发布于：</span>{{ formatDate(selected.created_at) }}</div>
              <div v-if="selected.license"><span class="text-[#9ca3af]">license：</span>{{ selected.license }}</div>
              <div v-if="selected.compatibility">
                <span class="text-[#9ca3af]">兼容性：</span>{{ selected.compatibility }}
              </div>
            </div>
            <p class="mb-4 rounded-lg bg-[#f9fafb] px-3 py-2 text-sm text-[#374151]">
              {{ selected.description }}
            </p>
          </div>

          <div class="flex-shrink-0 border-t border-[#e5e7eb] bg-white px-5 py-3">
            <p
              v-if="flashMsg"
              class="mb-2 rounded-lg border border-[#bbf7d0] bg-[#f0fdf4] px-3 py-2 text-xs text-[#166534]"
            >
              {{ flashMsg }}
            </p>
            <div class="flex items-center justify-between">
              <button
                v-if="isAuthor"
                class="rounded-lg px-3 py-1.5 text-sm text-[#9a3412] transition hover:bg-[#fff7ed] disabled:opacity-50"
                :disabled="deleting"
                type="button"
                @click="doDelete"
              >
                {{ deleting ? '删除中...' : '删除发布' }}
              </button>
              <div v-else />
              <div class="flex items-center gap-2">
                <select
                  v-model="selectedProjectId"
                  class="h-8 rounded-lg border border-[#d1d5db] bg-white px-2 text-sm text-[#374151] outline-none focus:border-[#9ca3af] focus:ring-2 focus:ring-[#9ca3af]/20"
                >
                  <option value="">选择项目</option>
                  <option v-for="project in projects" :key="project.pid" :value="project.pid">
                    {{ project.projectname }}
                  </option>
                </select>
                <button
                  class="rounded-lg border border-[#d1d5db] px-3 py-1.5 text-sm text-[#4b5563] transition hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="installingProject || !selectedProjectId"
                  type="button"
                  @click="doInstallProject"
                >
                  {{ installingProject ? '安装中...' : '安装到项目' }}
                </button>
                <button
                  class="rounded-lg bg-[#e5e7eb] px-4 py-1.5 text-sm text-[#374151] transition hover:bg-[#d1d5db] disabled:cursor-not-allowed disabled:bg-[#e5e7eb] disabled:text-[#9ca3af]"
                  :disabled="installing"
                  type="button"
                  @click="doInstall"
                >
                  {{ installing ? '安装中...' : '安装到我的技能' }}
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 批量上传 ZIP 弹窗 -->
    <div
      v-if="showUploadModal"
      class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 backdrop-blur-sm"
      @click.self="closeUploadModal"
    >
      <div class="flex h-[560px] w-[640px] max-w-[95vw] flex-col rounded-2xl bg-white shadow-xl overflow-hidden border border-[#e5e7eb]">
        <!-- 头部 -->
        <div class="flex h-14 flex-shrink-0 items-center justify-between border-b border-[#e5e7eb] px-5 bg-gray-50">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-gray-800">批量上传技能 ZIP</span>
            <span v-if="queueStats.total > 0" class="rounded-full bg-gray-200 px-2.5 py-0.5 text-xs text-gray-600">
              已选 {{ queueStats.total }}
            </span>
          </div>
          <button
            class="flex h-8 w-8 items-center justify-center rounded-lg text-[#6b7280] hover:bg-gray-200 hover:text-[#1f2937] transition"
            type="button"
            @click="closeUploadModal"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- 主体 -->
        <div class="min-h-0 flex-1 overflow-y-auto p-5 flex flex-col gap-4">
          <!-- 拖放区域 / 上传区域 -->
          <div
            :class="[
              'flex flex-col items-center justify-center border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all duration-200',
              isDragOver
                ? 'border-[#1f2937] bg-gray-50/80 scale-[0.99]'
                : 'border-gray-300 hover:border-gray-400 bg-gray-50/30'
            ]"
            @dragover="handleDragOver"
            @dragleave="handleDragLeave"
            @drop="handleDrop"
            @click="openUploadPicker"
          >
            <div class="flex flex-col items-center gap-2">
              <div class="p-3 bg-white rounded-full shadow-sm border border-gray-100 text-gray-400">
                <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <div>
                <span class="text-sm font-medium text-gray-700">点击选择</span>
                <span class="text-sm text-gray-500"> 或拖入技能 ZIP 文件到这里</span>
              </div>
              <span class="text-xs text-gray-400">每个文件大小限制在 40MB 以内</span>
            </div>
          </div>

          <!-- 进度条 -->
          <div v-if="queueStats.total > 0 && (isBatchUploading || queueStats.success > 0 || queueStats.error > 0)" class="bg-gray-50 border border-gray-100 rounded-xl p-3.5 flex flex-col gap-2">
            <div class="flex items-center justify-between text-xs text-gray-500 font-medium">
              <span>上传进度：{{ queueStats.success + queueStats.error }} / {{ queueStats.total }}</span>
              <span>{{ queueStats.progressPercent }}%</span>
            </div>
            <div class="h-2 w-full bg-gray-200 rounded-full overflow-hidden">
              <div
                class="h-full bg-[#1f2937] rounded-full transition-all duration-300 ease-out"
                :style="{ width: `${queueStats.progressPercent}%` }"
              />
            </div>
            <div class="flex gap-4 text-[10px] text-gray-400 font-medium">
              <span class="text-emerald-600">成功：{{ queueStats.success }}</span>
              <span class="text-rose-500">失败：{{ queueStats.error }}</span>
              <span v-if="queueStats.uploading > 0" class="text-[#1f2937] font-semibold animate-pulse">正在上传...</span>
            </div>
          </div>

          <!-- 文件队列 -->
          <div v-if="uploadQueue.length > 0" class="flex-1 min-h-0 flex flex-col gap-2">
            <div class="flex justify-between items-center text-xs text-gray-500 font-medium">
              <span>文件列表</span>
              <button
                class="text-rose-600 hover:text-rose-700 transition disabled:opacity-50 text-[11px]"
                :disabled="isBatchUploading"
                type="button"
                @click="clearQueue"
              >
                清空队列
              </button>
            </div>
            <div class="flex-1 min-h-0 overflow-y-auto border border-gray-100 rounded-xl bg-gray-50/50 p-2 divide-y divide-gray-100">
              <div
                v-for="item in uploadQueue"
                :key="item.id"
                class="flex items-center justify-between py-2 px-1 text-xs gap-3"
              >
                <div class="flex items-center gap-2 min-w-0 flex-1">
                  <!-- 文件图标 / 状态指示符 -->
                  <div class="flex-shrink-0">
                    <svg v-if="item.status === 'pending'" class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <svg v-else-if="item.status === 'uploading'" class="w-4 h-4 text-amber-500 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89" />
                    </svg>
                    <svg v-else-if="item.status === 'success'" class="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                    <svg v-else-if="item.status === 'error'" class="w-4 h-4 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                  <span class="truncate font-medium text-gray-700 min-w-0" :title="item.file.name">{{ item.file.name }}</span>
                  <span class="text-[10px] text-gray-400 flex-shrink-0 tabular-nums">{{ formatBytes(item.file.size) }}</span>
                </div>

                <div class="flex items-center gap-2 flex-shrink-0">
                  <span
                    v-if="item.error"
                    class="text-[10px] text-rose-600 bg-rose-50 border border-rose-100 rounded px-1.5 py-0.5 truncate max-w-[150px]"
                    :title="item.error"
                  >
                    {{ item.error }}
                  </span>
                  <button
                    v-if="item.status === 'pending' || item.status === 'error'"
                    class="p-1 text-gray-400 hover:text-rose-600 rounded transition"
                    :disabled="isBatchUploading"
                    type="button"
                    title="移除"
                    @click="removeQueueItem(item.id)"
                  >
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="flex-1 flex flex-col items-center justify-center text-gray-400 text-xs py-10">
            暂无待上传文件
          </div>
        </div>

        <!-- 尾部操作 -->
        <div class="flex-shrink-0 border-t border-[#e5e7eb] bg-white px-5 py-3 flex justify-end gap-2">
          <button
            class="rounded-lg border border-gray-300 px-4 py-1.5 text-sm text-[#374151] transition hover:bg-gray-50 disabled:opacity-50"
            :disabled="isBatchUploading"
            type="button"
            @click="closeUploadModal"
          >
            关闭
          </button>
          <button
            class="rounded-lg bg-[#1f2937] px-5 py-1.5 text-sm text-white font-medium transition hover:bg-[#111827] disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            :disabled="isBatchUploading || queueStats.pending === 0"
            type="button"
            @click="startBatchUpload"
          >
            <span v-if="isBatchUploading" class="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            {{ isBatchUploading ? '正在上传...' : '开始上传' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
