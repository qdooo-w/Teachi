<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  type UserLibrarySkill,
  type LibrarySkillSort,
  listLibrarySkills,
  getLibrarySkill,
  installLibrarySkill,
  forkLibrarySkill,
  getErrorMessage,
} from '../api'
import { useProjects } from '../composables/useProjects'
import { useNotification } from '../composables/useNotification'
import LibraryUploadDialog from '../components/LibraryUploadDialog.vue'

const { projects, loadProjects } = useProjects()
const { showError, showSuccess } = useNotification()

// ── 列表状态 ────────────────────────────────────────────────────────────
const skills = ref<UserLibrarySkill[]>([])
const total = ref(0)
const loading = ref(false)

// ── 搜索 / 筛选 / 排序 ──────────────────────────────────────────────────
const keyword = ref('')
const selectedTags = ref<string[]>([])
const showTagFilter = ref(false)
const tagInputText = ref('')
const tagInputRef = ref<HTMLInputElement | null>(null)
const sortBy = ref<LibrarySkillSort>('newest')

// ── 分页 ────────────────────────────────────────────────────────────────
const pageSize = 24
const currentPage = ref(1)

// ── 详情弹层 ────────────────────────────────────────────────────────────
const detailSkill = ref<UserLibrarySkill | null>(null)
const detailLoading = ref(false)
const installing = ref(false)
const installingProject = ref(false)
const forking = ref(false)
const selectedProjectId = ref('')

// ── 上传弹窗 ────────────────────────────────────────────────────────────
const showUploadDialog = ref(false)

// ── 标签解析 ────────────────────────────────────────────────────────────
function parseTags(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ── 格式化 ──────────────────────────────────────────────────────────────
function skillTitle(skill: UserLibrarySkill): string {
  return skill.display_name || skill.name
}

function sourceLabel(skill: UserLibrarySkill): string {
  return skill.community_skill_id ? '来自社区' : '本地收集'
}

function formatBytes(n: number | null | undefined): string {
  if (n == null || n <= 0) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function formatFullDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

// ── 加载（服务端筛选） ───────────────────────────────────────────────────
async function load(): Promise<void> {
  loading.value = true
  try {
    const r = await listLibrarySkills({
      keyword: keyword.value.trim() || undefined,
      tag: selectedTags.value.length > 0 ? selectedTags.value : undefined,
      sort: sortBy.value,
      limit: pageSize,
      offset: (currentPage.value - 1) * pageSize,
    })
    skills.value = r.skills
    total.value = r.total
  } catch (e) {
    showError('加载仓库失败', getErrorMessage(e))
  } finally {
    loading.value = false
  }
}

// ── 详情弹层 ────────────────────────────────────────────────────────────
async function openDetail(id: string): Promise<void> {
  detailLoading.value = true
  try {
    detailSkill.value = await getLibrarySkill(id)
  } catch (e) {
    showError('加载详情失败', getErrorMessage(e))
  } finally {
    detailLoading.value = false
  }
}

function closeDetail(): void {
  detailSkill.value = null
}

// ── 安装 ────────────────────────────────────────────────────────────────
async function doInstall(): Promise<void> {
  if (!detailSkill.value) return
  installing.value = true
  try {
    const r = await installLibrarySkill(detailSkill.value.id, { target: 'user' })
    showSuccess(`已安装到我的技能：${r.name}`)
  } catch (e) {
    showError('安装失败', getErrorMessage(e))
  } finally {
    installing.value = false
  }
}

async function doInstallProject(): Promise<void> {
  if (!detailSkill.value || !selectedProjectId.value) return
  installingProject.value = true
  try {
    const r = await installLibrarySkill(detailSkill.value.id, {
      target: 'project',
      pid: selectedProjectId.value,
    })
    const project = projects.value.find((p) => p.pid === selectedProjectId.value)
    showSuccess(`已安装到项目 ${project?.projectname ?? selectedProjectId.value}：${r.name}`)
  } catch (e) {
    showError('安装失败', getErrorMessage(e))
  } finally {
    installingProject.value = false
  }
}

// ── Fork ────────────────────────────────────────────────────────────────
async function doFork(): Promise<void> {
  if (!detailSkill.value) return
  forking.value = true
  try {
    const r = await forkLibrarySkill(detailSkill.value.id)
    showSuccess(`已 Fork：${skillTitle(r)}`)
    detailSkill.value = null
    await load()
  } catch (e) {
    showError('Fork 失败', getErrorMessage(e))
  } finally {
    forking.value = false
  }
}

// ── 标签筛选操作 ────────────────────────────────────────────────────────
function toggleTagFilter(): void {
  showTagFilter.value = !showTagFilter.value
  if (showTagFilter.value) {
    setTimeout(() => tagInputRef.value?.focus(), 50)
  }
}

function addTag(tag: string): void {
  const t = tag.trim()
  if (t && !selectedTags.value.includes(t)) {
    selectedTags.value.push(t)
    currentPage.value = 1
    void load()
  }
  tagInputText.value = ''
}

function removeTag(tag: string): void {
  selectedTags.value = selectedTags.value.filter((t) => t !== tag)
  currentPage.value = 1
  void load()
}

function handleTagInputKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter') {
    e.preventDefault()
    addTag(tagInputText.value)
  }
}

function changeSort(next: LibrarySkillSort): void {
  if (sortBy.value === next) return
  sortBy.value = next
  currentPage.value = 1
  void load()
}

// ── 分页 ────────────────────────────────────────────────────────────────
function gotoPage(page: number): void {
  currentPage.value = Math.max(1, Math.min(totalPages.value, page))
  void load()
}

const pageNumbers = computed(() => {
  const pages: number[] = []
  const tp = totalPages.value
  const cur = currentPage.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 3) pages.push(-1)
    for (let i = Math.max(2, cur - 1); i <= Math.min(tp - 1, cur + 1); i++) pages.push(i)
    if (cur < tp - 2) pages.push(-1)
    pages.push(tp)
  }
  return pages
})

// ── 生命周期 ────────────────────────────────────────────────────────────
onMounted(() => {
  document.title = '我的仓库 · Learnova'
  void load()
  void loadProjects()
})

// 关键词变化时回到第一页并重新加载
watch(keyword, () => {
  currentPage.value = 1
  void load()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-[#f3f4f6]">
    <!-- ═══ 搜索栏 ═══ -->
    <div class="relative flex h-14 flex-shrink-0 items-center justify-between bg-transparent px-6">
      <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-3">
        <div
          class="relative flex items-center bg-[#e5e7eb]/70 hover:bg-[#e5e7eb] focus-within:bg-white focus-within:ring-2 focus-within:ring-[#9ca3af]/20 transition-all rounded-2xl w-72 h-8"
        >
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <svg class="h-4 w-4 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <input
            v-model="keyword"
            class="block w-full rounded-2xl bg-transparent py-1 pl-9 pr-3 text-sm text-[#1f2937] placeholder:text-[#9ca3af] outline-none"
            placeholder="搜索仓库技能..."
            type="search"
          />
        </div>
      </div>

      <!-- 上传 ZIP -->
      <div class="ml-auto">
        <button
          class="flex h-8 w-8 items-center justify-center rounded-full bg-[#1f2937] text-white transition-all duration-200 hover:bg-[#111827] active:scale-95"
          type="button"
          @click="showUploadDialog = true"
        >
          <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0L8 8m4-4l4 4M4 18h16" />
          </svg>
        </button>
      </div>
    </div>

    <!-- ═══ 筛选栏 ═══ -->
    <div class="flex flex-shrink-0 items-center gap-2 px-5 py-2 bg-white">
      <!-- 排序 -->
      <select
        class="h-7 !text-xs font-hans border-0 border-b-2 border-[#e5e7eb] hover:border-[#1f2937] rounded-none bg-transparent pl-0 pr-3 text-[#4b5563] outline-none cursor-pointer appearance-none"
        :value="sortBy"
        @change="changeSort(($event.target as HTMLSelectElement).value as LibrarySkillSort)"
        style="background-image: url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2210%22 height=%226%22 fill=%22none%22%3E%3Cpath stroke=%22%236b7280%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 stroke-width=%221.5%22 d=%22M1 1l4 4 4-4%22/%3E%3C/svg%3E'); background-repeat: no-repeat; background-position: right 0 center;"
      >
        <option value="newest">最新</option>
        <option value="oldest">最早</option>
        <option value="name-asc">名称 A-Z</option>
        <option value="name-desc">名称 Z-A</option>
      </select>

      <!-- 标签筛选 -->
      <button
        type="button"
        class="flex items-center gap-1 h-7 !text-xs font-hans border-0 border-b-2 rounded-none pl-0 pr-2 transition-colors"
        :class="showTagFilter || selectedTags.length > 0 ? 'border-[#1f2937] text-[#1f2937]' : 'border-[#e5e7eb] text-[#6b7280] hover:border-[#1f2937] hover:text-[#1f2937]'"
        @click="toggleTagFilter"
      >
        <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
        </svg>
        <span>标签</span>
      </button>

      <!-- 已选标签 chips -->
      <template v-for="tag in selectedTags" :key="tag">
        <span class="inline-flex items-center gap-1 bg-[#e5e7eb] rounded-sm px-2 py-0.5 !text-xs font-hans text-[#4b5563]">
          {{ tag }}
          <button type="button" class="text-[#9ca3af] hover:text-[#1f2937]" @click="removeTag(tag)">
            <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </span>
      </template>

      <!-- 标签输入 -->
      <div v-if="showTagFilter" class="flex items-center">
        <input
          ref="tagInputRef"
          v-model="tagInputText"
          class="w-28 h-7 !text-xs font-hans border-0 border-b-2 border-[#e5e7eb] focus:border-[#1f2937] rounded-none bg-transparent pl-0 pr-2 text-[#4b5563] placeholder:text-[#9ca3af] outline-none"
          placeholder="输入标签回车"
          @keydown="handleTagInputKeydown"
        />
      </div>

      <div class="flex-1" />
      <span class="text-xs text-[#9ca3af] font-hans">共 {{ total }} 个技能</span>
    </div>

    <!-- ═══ 卡片网格 ═══ -->
    <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
      <div v-if="loading" class="py-16 text-center text-sm text-[#9ca3af]">加载中...</div>

      <div v-else-if="skills.length === 0" class="py-16 text-center text-sm text-[#9ca3af]">
        仓库中还没有技能，从技能管理页收集或从社区安装吧。
      </div>

      <div v-else class="flex flex-wrap gap-3">
        <button
          v-for="s in skills"
          :key="s.id"
          class="flex w-[224px] flex-col gap-2 rounded-xl bg-white p-3.5 text-left shadow-sm transition hover:bg-[#f9fafb] hover:shadow-md active:scale-[0.99]"
          type="button"
          @click="openDetail(s.id)"
        >
          <!-- 标题行 -->
          <div class="flex items-start justify-between gap-2">
            <span class="truncate text-sm font-semibold text-[#1f2937]">{{ skillTitle(s) }}</span>
            <span
              class="flex flex-shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] whitespace-nowrap"
              :class="s.community_skill_id ? 'bg-blue-50 text-blue-600' : 'bg-[#f3f4f6] text-[#6b7280]'"
            >
              {{ sourceLabel(s) }}
            </span>
          </div>

          <!-- 描述 -->
          <p class="line-clamp-2 text-xs text-[#6b7280] leading-relaxed">
            {{ s.description || '无描述' }}
          </p>

          <!-- 底部：标签 + 版本 + 大小 -->
          <div class="mt-auto flex items-center justify-between gap-2">
            <div class="flex items-center gap-1.5 min-w-0 overflow-hidden">
              <template v-for="tag in parseTags(s.tags).slice(0, 2)" :key="tag">
                <span class="rounded-sm bg-[#f3f4f6] px-1.5 py-0.5 text-[10px] text-[#9ca3af] truncate max-w-[60px]">
                  {{ tag }}
                </span>
              </template>
            </div>
            <div class="flex flex-shrink-0 items-center gap-1.5 text-[10px] text-[#9ca3af] tabular-nums">
              <span>v{{ s.version }}</span>
              <span>·</span>
              <span>{{ formatBytes(s.size_bytes) }}</span>
            </div>
          </div>
        </button>
      </div>

      <!-- 分页 -->
      <div v-if="totalPages > 1" class="mt-5 mb-4 flex items-center justify-center gap-1.5">
        <button
          class="flex h-8 w-8 items-center justify-center rounded-lg text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.97] disabled:opacity-40"
          :disabled="currentPage === 1"
          type="button"
          @click="gotoPage(currentPage - 1)"
        >
          <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <template v-for="p in pageNumbers" :key="p">
          <span v-if="p === -1" class="px-1 text-xs text-[#9ca3af]">...</span>
          <button
            v-else
            class="flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium transition-all duration-200 active:scale-[0.97]"
            :class="p === currentPage ? 'bg-[#1f2937] text-white' : 'text-[#6b7280] hover:bg-[#e5e7eb]'"
            type="button"
            @click="gotoPage(p)"
          >
            {{ p }}
          </button>
        </template>
        <button
          class="flex h-8 w-8 items-center justify-center rounded-lg text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.97] disabled:opacity-40"
          :disabled="currentPage === totalPages"
          type="button"
          @click="gotoPage(currentPage + 1)"
        >
          <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      </div>
    </div>

    <!-- ═══ 上传弹窗 ═══ -->
    <LibraryUploadDialog
      v-if="showUploadDialog"
      @close="showUploadDialog = false"
      @done="showUploadDialog = false; load()"
    />

    <!-- ═══ 详情弹层 ═══ -->
    <Transition name="dialog-fade" appear>
      <div
        v-if="detailSkill || detailLoading"
        class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 backdrop-blur-sm"
        @click.self="closeDetail"
      >
        <div class="modal-card font-hans flex h-[600px] w-[720px] max-w-[95vw] flex-col rounded-2xl bg-white shadow-xl">
          <!-- 标题栏 -->
          <div class="flex h-14 flex-shrink-0 items-center justify-between px-5 bg-[#f9fafb] rounded-t-2xl border-b border-[#e5e7eb]">
            <div class="flex items-center gap-3">
              <span class="font-semibold text-[#1f2937]">
                {{ detailSkill ? skillTitle(detailSkill) : '加载中...' }}
              </span>
              <span
                v-if="detailSkill"
                class="rounded-full px-2 py-0.5 text-[10px]"
                :class="detailSkill.community_skill_id ? 'bg-blue-50 text-blue-600' : 'bg-[#f3f4f6] text-[#6b7280]'"
              >
                {{ sourceLabel(detailSkill) }}
              </span>
            </div>
            <button
              class="flex h-8 w-8 items-center justify-center rounded-full text-[#6b7280] transition-all duration-200 active:scale-90 hover:bg-[#e5e7eb] hover:text-[#1f2937]"
              type="button"
              @click="closeDetail"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div v-if="!detailSkill" class="flex flex-1 items-center justify-center text-sm text-[#9ca3af]">
            加载中...
          </div>
          <template v-else>
            <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <div class="mb-4 grid grid-cols-[70px_1fr] gap-x-3 gap-y-1.5 text-xs">
                <span class="text-[#9ca3af]">名称</span>
                <span class="text-[#1f2937] font-medium">{{ detailSkill.name }}</span>
                <span class="text-[#9ca3af]">显示名</span>
                <span class="text-[#1f2937]">{{ detailSkill.display_name || '-' }}</span>
                <span class="text-[#9ca3af]">版本</span>
                <span class="text-[#1f2937]">v{{ detailSkill.version }}</span>
                <span class="text-[#9ca3af]">大小</span>
                <span class="text-[#1f2937]">{{ formatBytes(detailSkill.size_bytes) }}</span>
                <span class="text-[#9ca3af]">标签</span>
                <span class="text-[#1f2937]">
                  <template v-if="parseTags(detailSkill.tags).length > 0">
                    <span
                      v-for="tag in parseTags(detailSkill.tags)"
                      :key="tag"
                      class="mr-1 rounded-sm bg-[#f3f4f6] px-1.5 py-0.5 text-[11px] text-[#6b7280]"
                    >{{ tag }}</span>
                  </template>
                  <span v-else class="text-[#9ca3af]">-</span>
                </span>
                <span class="text-[#9ca3af]">来源</span>
                <span class="text-[#1f2937]">{{ sourceLabel(detailSkill) }}</span>
                <span class="text-[#9ca3af]">创建</span>
                <span class="text-[#1f2937]">{{ formatFullDate(detailSkill.created_at) }}</span>
                <span class="text-[#9ca3af]">更新</span>
                <span class="text-[#1f2937]">{{ formatFullDate(detailSkill.updated_at) }}</span>
                <template v-if="detailSkill.changelog">
                  <span class="text-[#9ca3af]">变更</span>
                  <span class="text-[#1f2937]">{{ detailSkill.changelog }}</span>
                </template>
              </div>

              <p v-if="detailSkill.description" class="mb-4 rounded-lg bg-[#f9fafb] px-3 py-2 text-sm text-[#374151] leading-relaxed">
                {{ detailSkill.description }}
              </p>

              <div v-if="detailSkill.readme_md" class="mt-4">
                <div class="mb-2 text-xs font-semibold text-[#9ca3af] uppercase tracking-wider">README</div>
                <div class="rounded-xl border border-[#e5e7eb] bg-[#fafafa] p-4 text-sm text-[#374151] leading-relaxed max-h-[240px] overflow-y-auto">
                  <pre class="whitespace-pre-wrap font-sans text-sm text-[#374151]">{{ detailSkill.readme_md }}</pre>
                </div>
              </div>
            </div>

            <div class="flex-shrink-0 bg-[#f9fafb] rounded-b-2xl px-5 py-3.5 border-t border-[#e5e7eb]">
              <div class="flex items-center justify-between">
                <button
                  class="rounded-xl bg-[#f3f4f6] px-4 py-2 text-sm text-[#374151] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="forking"
                  type="button"
                  @click="doFork"
                >
                  {{ forking ? 'Fork 中...' : 'Fork' }}
                </button>

                <div class="flex items-center gap-2">
                  <select
                    v-model="selectedProjectId"
                    class="h-9 max-w-[160px] rounded-xl bg-white px-3 text-sm text-[#374151] outline-none shadow-sm focus:ring-2 focus:ring-[#1f2937]/20"
                  >
                    <option value="">选择项目</option>
                    <option v-for="project in projects" :key="project.pid" :value="project.pid">
                      {{ project.projectname }}
                    </option>
                  </select>
                  <button
                    class="h-9 rounded-xl bg-[#f3f4f6] px-4 text-sm text-[#374151] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="installingProject || !selectedProjectId"
                    type="button"
                    @click="doInstallProject"
                  >
                    {{ installingProject ? '安装中...' : '安装到项目' }}
                  </button>
                  <button
                    class="h-9 rounded-xl bg-[#1f2937] px-4 text-sm text-white font-semibold transition-all duration-200 hover:bg-[#111827] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
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
    </Transition>
  </div>
</template>
