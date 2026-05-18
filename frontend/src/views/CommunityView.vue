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
  getCurrentUserId,
  getErrorMessage,
} from '../api'

const router = useRouter()

const currentUserId = ref<string | null>(getCurrentUserId())

const skills = ref<CommunitySkillSummary[]>([])
const total = ref(0)
const loading = ref(false)
const errorMsg = ref('')

const keyword = ref('')
const sort = ref<CommunitySort>('popular')
const limit = 20
const offset = ref(0)

const selected = ref<CommunitySkillDetail | null>(null)
const detailLoading = ref(false)
const installing = ref(false)
const deleting = ref(false)
const flashMsg = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const currentPage = computed(() => Math.floor(offset.value / limit) + 1)
const isAuthor = computed(() => selected.value?.owner_uuid === currentUserId.value)

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

async function doDelete(): Promise<void> {
  if (!selected.value) return
  if (!confirm(`确定要删除社区中的 "${selected.value.name}" 吗？此操作不可撤销。`)) return
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

onMounted(() => {
  document.title = '社区 · Teachi'
  void load()
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
          v-model="keyword"
          class="h-9 w-64 rounded-md border border-[#d1d5db] px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
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
            sort === 'popular' ? 'bg-[#e6f4ee] font-medium text-[#1f6f5b]' : 'text-[#6b7280] hover:bg-[#f3f4f6]',
          ]"
          type="button"
          @click="changeSort('popular')"
        >
          热门
        </button>
        <button
          :class="[
            'rounded-md px-3 py-1 text-xs transition',
            sort === 'newest' ? 'bg-[#e6f4ee] font-medium text-[#1f6f5b]' : 'text-[#6b7280] hover:bg-[#f3f4f6]',
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

      <div v-if="loading" class="py-16 text-center text-sm text-[#9ca3af]">加载中...</div>
      <div v-else-if="skills.length === 0" class="py-16 text-center text-sm text-[#9ca3af]">
        还没有技能，去技能管理页发布第一个吧。
      </div>

      <div v-else class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <button
          v-for="s in skills"
          :key="s.id"
          class="flex flex-col gap-2 rounded-lg border border-[#e5e7eb] bg-white p-4 text-left transition hover:border-[#1f6f5b]/40 hover:shadow-sm"
          type="button"
          @click="openDetail(s.id)"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="truncate text-sm font-semibold text-[#1f2937]">{{ s.name }}</span>
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
            <span class="font-semibold text-[#1f2937]">{{ selected?.name ?? '加载中...' }}</span>
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
            <pre class="whitespace-pre-wrap rounded-md border border-[#e5e7eb] bg-[#fafafa] p-3 font-mono text-xs leading-relaxed text-[#374151]">{{ selected.body_md }}</pre>
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
              <button
                class="rounded-md bg-[#1f6f5b] px-4 py-1.5 text-sm text-white transition hover:bg-[#1a5b4a] disabled:cursor-not-allowed disabled:bg-[#9ca3af]"
                :disabled="installing"
                type="button"
                @click="doInstall"
              >
                {{ installing ? '安装中...' : '安装到我的技能' }}
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
