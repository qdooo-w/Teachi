<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
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

const router = useRouter()
const { projects, loadProjects } = useProjects()

const currentUserId = ref<string | null>(getCurrentUserId())

const skills = ref<CommunitySkillSummary[]>([])
const total = ref(0)
const loading = ref(false)
const errorMsg = ref('')

const keyword = ref('')
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
const uploading = ref(false)
const uploadMsg = ref('')
const uploadMsgKind = ref<'success' | 'error'>('success')

const MAX_UPLOAD_ZIP_BYTES = COMMUNITY_MAX_UPLOAD_BYTES

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

function openUploadPicker(): void {
  uploadMsg.value = ''
  uploadMsgKind.value = 'success'
  uploadInput.value?.click()
}

async function handleZipUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  uploadMsg.value = ''
  uploadMsgKind.value = 'success'
  if (!file.name.toLowerCase().endsWith('.zip')) {
    uploadMsg.value = '只允许上传 zip 文件。'
    uploadMsgKind.value = 'error'
    return
  }
  if (file.size > MAX_UPLOAD_ZIP_BYTES) {
    uploadMsg.value = '单个 zip 包不能超过 40MB。'
    uploadMsgKind.value = 'error'
    return
  }

  uploading.value = true
  try {
    const published = await uploadCommunitySkillZip(file)
    uploadMsg.value = `已上传并发布：${skillTitle(published)}`
    uploadMsgKind.value = 'success'
    offset.value = 0
    await load()
    await openDetail(published.id)
  } catch (e) {
    uploadMsg.value = getErrorMessage(e)
    uploadMsgKind.value = 'error'
  } finally {
    uploading.value = false
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

onMounted(() => {
  document.title = '社区 · Teachi'
  void load()
  void loadProjects()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-[#f9fafb]">
    <header class="flex flex-shrink-0 items-center justify-between border-b border-[#e5e7eb] bg-white px-6 py-3">
      <div class="flex items-center gap-3">
        <button
          class="flex h-8 w-8 items-center justify-center rounded-md text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#1f2937]"
          type="button"
          title="返回总览"
          @click="router.push({ name: 'overview' })"
        >
          <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <h1 class="text-lg font-semibold text-[#1f2937]">技能社区</h1>
      </div>
      <div class="flex items-center gap-2">
        <input
          ref="uploadInput"
          class="hidden"
          accept=".zip,application/zip,application/x-zip-compressed"
          type="file"
          @change="handleZipUpload"
        />
        <button
          class="h-9 rounded-md border border-[#d1d5db] px-3 text-sm text-[#374151] transition hover:border-[#d1d5db] hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="uploading"
          type="button"
          title="上传技能 zip"
          @click="openUploadPicker"
        >
          {{ uploading ? '上传中...' : '上传 ZIP' }}
        </button>
        <input
          v-model="keyword"
          class="h-9 w-64 rounded-md border border-[#d1d5db] px-3 text-sm outline-none transition focus:border-[#9ca3af] focus:ring-2 focus:ring-[#9ca3af]/20"
          placeholder="搜索技能名或描述"
          type="search"
          @keyup.enter="submitSearch"
        />
        <button
          class="h-9 rounded-md bg-[#1f2937] px-4 text-sm text-white transition hover:bg-[#111827]"
          type="button"
          @click="submitSearch"
        >
          搜索
        </button>
      </div>
    </header>

    <div class="flex flex-shrink-0 items-center justify-between border-b border-[#e5e7eb] bg-white px-6 py-2 text-sm">
      <div class="flex items-center gap-1">
        <span class="mr-2 text-xs text-[#9ca3af]">排序</span>
        <button
          :class="[
            'rounded-md px-3 py-1 text-xs transition',
            sort === 'popular' ? 'bg-[#f3f4f6] font-medium text-[#4b5563]' : 'text-[#6b7280] hover:bg-[#f3f4f6]',
          ]"
          type="button"
          @click="changeSort('popular')"
        >
          热门
        </button>
        <button
          :class="[
            'rounded-md px-3 py-1 text-xs transition',
            sort === 'newest' ? 'bg-[#f3f4f6] font-medium text-[#4b5563]' : 'text-[#6b7280] hover:bg-[#f3f4f6]',
          ]"
          type="button"
          @click="changeSort('newest')"
        >
          最新
        </button>
      </div>
      <span class="text-xs text-[#9ca3af]">共 {{ total }} 个技能</span>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <p
        v-if="errorMsg"
        class="mb-4 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]"
      >
        {{ errorMsg }}
      </p>
      <p
        v-if="uploadMsg"
        :class="[
          'mb-4 rounded-md border px-3 py-2 text-sm',
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

      <div v-else class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <button
          v-for="s in skills"
          :key="s.id"
          class="flex flex-col gap-2 rounded-lg border border-[#e5e7eb] bg-white p-4 text-left transition hover:border-[#d1d5db] hover:shadow-sm"
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
          class="rounded-md border border-[#e5e7eb] px-3 py-1 text-xs text-[#6b7280] disabled:opacity-50 hover:bg-[#f3f4f6]"
          :disabled="currentPage === 1"
          type="button"
          @click="gotoPage(currentPage - 1)"
        >
          上一页
        </button>
        <span class="text-xs tabular-nums text-[#9ca3af]">{{ currentPage }} / {{ totalPages }}</span>
        <button
          class="rounded-md border border-[#e5e7eb] px-3 py-1 text-xs text-[#6b7280] disabled:opacity-50 hover:bg-[#f3f4f6]"
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
            class="flex h-8 w-8 items-center justify-center rounded-md text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#1f2937]"
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
            <p class="mb-4 rounded-md bg-[#f9fafb] px-3 py-2 text-sm text-[#374151]">
              {{ selected.description }}
            </p>
          </div>

          <div class="flex-shrink-0 border-t border-[#e5e7eb] bg-white px-5 py-3">
            <p
              v-if="flashMsg"
              class="mb-2 rounded-md border border-[#bbf7d0] bg-[#f0fdf4] px-3 py-2 text-xs text-[#166534]"
            >
              {{ flashMsg }}
            </p>
            <div class="flex items-center justify-between">
              <button
                v-if="isAuthor"
                class="rounded-md px-3 py-1.5 text-sm text-[#9a3412] transition hover:bg-[#fff7ed] disabled:opacity-50"
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
                  class="h-8 rounded-md border border-[#d1d5db] bg-white px-2 text-sm text-[#374151] outline-none focus:border-[#9ca3af] focus:ring-2 focus:ring-[#9ca3af]/20"
                >
                  <option value="">选择项目</option>
                  <option v-for="project in projects" :key="project.pid" :value="project.pid">
                    {{ project.projectname }}
                  </option>
                </select>
                <button
                  class="rounded-md border border-[#d1d5db] px-3 py-1.5 text-sm text-[#4b5563] transition hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="installingProject || !selectedProjectId"
                  type="button"
                  @click="doInstallProject"
                >
                  {{ installingProject ? '安装中...' : '安装到项目' }}
                </button>
                <button
                  class="rounded-md bg-[#e5e7eb] px-4 py-1.5 text-sm text-[#374151] transition hover:bg-[#d1d5db] disabled:cursor-not-allowed disabled:bg-[#e5e7eb] disabled:text-[#9ca3af]"
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
  </div>
</template>
