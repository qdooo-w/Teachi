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
  getCurrentUserId,
  getErrorMessage,
} from '../api'
import { COMMUNITY_PAGE_LIMIT } from '../config'
import { useProjects } from '../composables/useProjects'

const { projects, loadProjects } = useProjects()

const currentUserId = ref<string | null>(getCurrentUserId())

const skills = ref<CommunitySkillSummary[]>([])
const total = ref(0)
const loading = ref(false)
const errorMsg = ref('')

import { useCommunity } from '../composables/useCommunity'

const { searchQuery: keyword, triggerSearch } = useCommunity()
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

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const currentPage = computed(() => Math.floor(offset.value / limit) + 1)
const isAuthor = computed(() => selected.value?.owner_uuid === currentUserId.value)

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
  document.title = '社区 · Learnova'
  void load()
  void loadProjects()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-transparent">
    <!-- 搜索及上传控制栏 -->
    <div class="relative flex h-14 flex-shrink-0 items-center justify-between px-6 bg-transparent">
      <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-3">
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
          class="rounded-xl border border-[#e5e7eb] px-3.5 py-1.5 text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#f3f4f6] active:scale-[0.98] disabled:opacity-50"
          :disabled="currentPage === 1"
          type="button"
          @click="gotoPage(currentPage - 1)"
        >
          上一页
        </button>
        <span class="text-xs tabular-nums text-[#9ca3af]">{{ currentPage }} / {{ totalPages }}</span>
        <button
          class="rounded-xl border border-[#e5e7eb] px-3.5 py-1.5 text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#f3f4f6] active:scale-[0.98] disabled:opacity-50"
          :disabled="currentPage === totalPages"
          type="button"
          @click="gotoPage(currentPage + 1)"
        >
          下一页
        </button>
      </div>
    </div>

    <Transition name="dialog-fade" appear>
      <div
        v-if="selected || detailLoading"
        class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 backdrop-blur-sm"
        @click.self="closeDetail"
      >
        <div class="modal-card flex h-[640px] w-[760px] max-w-[95vw] flex-col rounded-2xl bg-white shadow-xl">
          <div class="flex h-14 flex-shrink-0 items-center justify-between px-5 bg-[#f9fafb] rounded-t-2xl">
            <div class="flex items-center gap-3">
              <span class="font-semibold text-[#1f2937]">{{ selected ? skillTitle(selected) : '加载中...' }}</span>
              <span
                v-if="selected"
                class="flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-[10px] tabular-nums text-[#6b7280] shadow-sm"
              >
                ⬇ {{ selected.downloads }}
              </span>
            </div>
            <button
              class="flex h-8 w-8 items-center justify-center rounded-full text-[#6b7280] transition-all duration-200 active:scale-90 hover:bg-[#e5e7eb] hover:text-[#1f2937]"
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

            <div class="flex-shrink-0 bg-[#f9fafb] rounded-b-2xl px-5 py-3.5">
              <p
                v-if="flashMsg"
                class="mb-2 rounded-lg bg-[#f0fdf4] px-3 py-2 text-xs text-[#166534]"
              >
                {{ flashMsg }}
              </p>
              <div class="flex items-center justify-between">
                <button
                  v-if="isAuthor"
                  class="rounded-xl bg-[#b91c1c] hover:bg-[#991b1b] active:scale-[0.98] text-white px-4 py-2 text-sm font-semibold transition-all duration-200 disabled:opacity-50"
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
                    class="h-9 max-w-[160px] rounded-xl bg-white px-3 text-sm text-[#374151] outline-none shadow-sm focus:ring-2 focus:ring-[#1f2937]/20"
                  >
                    <option value="">选择项目</option>
                    <option v-for="project in projects" :key="project.pid" :value="project.pid">
                      {{ project.projectname }}
                    </option>
                  </select>
                  <button
                    class="h-9 rounded-xl bg-[#f3f4f6] px-4 text-sm text-[#374151] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 shadow-sm"
                    :disabled="installingProject || !selectedProjectId"
                    type="button"
                    @click="doInstallProject"
                  >
                    {{ installingProject ? '安装中...' : '安装到项目' }}
                  </button>
                  <button
                    class="h-9 rounded-xl bg-[#1f2937] px-4 text-sm text-white font-semibold transition-all duration-200 hover:bg-[#111827] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 shadow-sm"
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
