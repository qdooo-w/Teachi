<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import RowMenu from '../components/RowMenu.vue'
import RenameInline from '../components/RenameInline.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import {
  createProject,
  deleteProject,
  getCurrentUserId,
  getErrorMessage,
  renameProject,
  type ProjectItem,
} from '../api'
import { useProjects } from '../composables/useProjects'
import { useLayout } from '../composables/useLayout'
import { writeSkill, PROJECT_DESC_SKILL, buildProjectDescSkill } from '../skills'

const router = useRouter()
const { projects, loadProjects, prependProject, upsertProject, removeProject } = useProjects()
const { closeSidebarOnMobile } = useLayout()

const cardScroller = ref<HTMLElement | null>(null)
const swapContainer = ref<HTMLElement | null>(null)
const scrollArea = ref<HTMLElement | null>(null)
const contentBox = ref<HTMLElement | null>(null)
const expanded = ref(false)
const titleVisible = ref(true)
const contentPaddingTop = ref(0)

// 过量滚动检测：滚动到底后继续滚动触发展开
const overscrollX = ref(0)
const EXPAND_THRESHOLD = 150
let overscrollResetTimer: ReturnType<typeof setTimeout> | null = null

function recalcPadding(): void {
  if (!scrollArea.value || !contentBox.value) return
  const areaH = scrollArea.value.clientHeight
  // 量子元素实际高度，排除 min-h-full 撑开的影响
  let childH = 0
  for (const child of contentBox.value.children) {
    childH += (child as HTMLElement).offsetHeight
  }
  // 外层容器有 py-5（20px top + 20px bottom）和 pb-28（112px bottom）
  const verticalPad = 20 + 20 + 112
  contentPaddingTop.value = Math.max(0, Math.floor((areaH - verticalPad - childH) / 2))
}

function onCardWheel(e: WheelEvent): void {
  if (!cardScroller.value) return
  e.preventDefault()
  const el = cardScroller.value
  const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 2

  // 右滑过量：滚动到底后继续向右
  if (atEnd && e.deltaY > 0) {
    overscrollX.value = Math.min(overscrollX.value + e.deltaY * 0.4, EXPAND_THRESHOLD + 40)
    clearTimeout(overscrollResetTimer!)
    overscrollResetTimer = setTimeout(() => { overscrollX.value = 0 }, 180)
    if (overscrollX.value >= EXPAND_THRESHOLD) {
      overscrollX.value = 0
      expand()
    }
    return
  }

  // 正常滚动：重置过量并滚动卡片
  overscrollX.value = 0
  el.scrollLeft += e.deltaY
}

// 展开：标题先淡出，然后切换视图，列表进场完毕后标题以小字淡入
async function expand(): Promise<void> {
  titleVisible.value = false
  contentPaddingTop.value = 40  // 展开后靠上，对应 pt-10
  await new Promise<void>((r) => setTimeout(r, 180))
  expanded.value = true
}

// 收起：标题先淡出，切换回卡片，再淡入大字
async function collapse(): Promise<void> {
  titleVisible.value = false
  await new Promise<void>((r) => setTimeout(r, 180))
  expanded.value = false
  recalcPadding()
  await new Promise<void>((r) => setTimeout(r, 50))
  titleVisible.value = true
}

// 离场前锁住容器高度，防止列表进场时布局塌陷
function onBeforeSwapLeave(el: Element): void {
  if (swapContainer.value) {
    swapContainer.value.style.minHeight = `${(el as HTMLElement).offsetHeight}px`
  }
}

// 离场元素脱离文档流，让列表可以同时进场
function onSwapLeave(el: Element): void {
  const h = el as HTMLElement
  h.style.position = 'absolute'
  h.style.top = '0'
  h.style.left = '0'
  h.style.width = '100%'
}

// 列表进场完毕后释放高度锁，标题淡入
function onSwapAfterEnter(): void {
  if (swapContainer.value) swapContainer.value.style.minHeight = ''
  titleVisible.value = true
}


const showCreatePanel = ref(false)
const newProjectName = ref('')
const newProjectDesc = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const creatingProject = ref(false)
const errorMessage = ref('')

const DESC_MAX = 100

async function openCreatePanel(): Promise<void> {
  showCreatePanel.value = true
  await nextTick()
  nameInput.value?.focus()
}

function closeCreatePanel(): void {
  if (creatingProject.value) return
  showCreatePanel.value = false
  newProjectName.value = ''
  newProjectDesc.value = ''
  errorMessage.value = ''
}

async function handleCreateProject(): Promise<void> {
  const name = newProjectName.value.trim()
  if (!name || creatingProject.value) return
  const userId = getCurrentUserId()
  if (!userId) return

  creatingProject.value = true
  errorMessage.value = ''
  try {
    const project = await createProject(userId, name)
    prependProject(project)

    const desc = newProjectDesc.value.trim()
    if (desc) {
      const space = { kind: 'project' as const, pid: project.pid }
      await writeSkill(space, PROJECT_DESC_SKILL, buildProjectDescSkill('', desc))
    }

    closeCreatePanel()
    closeSidebarOnMobile()
    await router.push({ name: 'subject', params: { pid: project.pid } })
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    creatingProject.value = false
  }
}

// ── 卡片菜单 ──────────────────────────────────────────────────────────────────
const openMenuKey = ref<string | null>(null)
const renamingKey = ref<string | null>(null)
const renameSubmitting = ref(false)
const confirmDelete = ref<{ id: string; name: string } | null>(null)
const deleteSubmitting = ref(false)
const deleteError = ref('')

function cardKey(pid: string): string {
  return `card:project:${pid}`
}
function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('zh-CN')
}
function toggleMenu(key: string): void { openMenuKey.value = openMenuKey.value === key ? null : key }
function closeMenu(): void { openMenuKey.value = null }
function startRename(key: string): void { renamingKey.value = key; openMenuKey.value = null }
function cancelRename(): void { renamingKey.value = null }

async function goToProject(project: ProjectItem): Promise<void> {
  closeSidebarOnMobile()
  await router.push({ name: 'subject', params: { pid: project.pid } })
}

async function submitProjectRename(project: ProjectItem, nextName: string): Promise<void> {
  renameSubmitting.value = true
  errorMessage.value = ''
  try {
    const updated = await renameProject(project.pid, nextName)
    upsertProject(updated)
    renamingKey.value = null
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    renameSubmitting.value = false
  }
}

function askDeleteProject(project: ProjectItem): void {
  openMenuKey.value = null
  deleteError.value = ''
  confirmDelete.value = { id: project.pid, name: project.projectname }
}
function cancelDelete(): void {
  if (deleteSubmitting.value) return
  confirmDelete.value = null
  deleteError.value = ''
}
async function performDelete(): Promise<void> {
  if (!confirmDelete.value || deleteSubmitting.value) return
  const target = confirmDelete.value
  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    await deleteProject(target.id)
    removeProject(target.id)
    confirmDelete.value = null
  } catch (error) {
    deleteError.value = getErrorMessage(error)
  } finally {
    deleteSubmitting.value = false
  }
}

function scrollToMiddleCard(): void {
  if (!cardScroller.value || projects.value.length === 0) return
  const cards = cardScroller.value.children
  const mid = Math.floor(cards.length / 2)
  const target = cards[mid] as HTMLElement | undefined
  if (!target) return
  const offset = target.offsetLeft - (cardScroller.value.clientWidth - target.clientWidth) / 2
  cardScroller.value.scrollTo({ left: offset, behavior: 'smooth' })
}

onMounted(async () => {
  if (projects.value.length === 0) await loadProjects()
  nextTick(() => {
    recalcPadding()
    scrollToMiddleCard()
  })
})
</script>

<template>
  <div class="absolute inset-0">
    <!-- 可滚动内容区，底部留出面板高度的空间 -->
    <div ref="scrollArea" class="absolute inset-0 overflow-y-auto px-4 py-5 md:px-6">
      <div
        ref="contentBox"
        class="mx-auto flex min-h-full w-full max-w-3xl flex-col pb-28"
        :style="{ paddingTop: contentPaddingTop + 'px', transition: 'padding-top 380ms cubic-bezier(0.4,0,0.2,1)' }"
      >
        <!-- 标题：展开时淡出，列表进场完毕后以小字淡入 -->
        <h1
          :class="[
            'font-bold',
            expanded ? 'mb-8 cursor-pointer text-3xl hover:opacity-70' : 'mb-10 text-4xl tracking-tight md:text-5xl',
          ]"
          :style="{ opacity: titleVisible ? 1 : 0, transition: 'opacity 200ms ease' }"
          @click="expanded && collapse()"
        >科目总览</h1>

        <!-- 卡片/列表切换容器：同时进出场，离场元素脱流 -->
        <div ref="swapContainer" class="relative">
          <Transition
            name="ov-swap"
            @before-leave="onBeforeSwapLeave"
            @leave="onSwapLeave"
            @after-enter="onSwapAfterEnter"
          >
            <!-- 卡片视图（不含箭头） -->
            <div v-if="!expanded" key="cards">
              <div
                v-if="projects.length > 0"
                ref="cardScroller"
                class="card-scroller no-scrollbar -mx-10 flex gap-4 overflow-x-auto px-10 pb-2 md:-mx-14 md:px-14"
                :style="{
                  transform: overscrollX > 0 ? `translateX(${-overscrollX * 0.3}px)` : '',
                  transition: overscrollX > 0 ? 'none' : 'transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1)',
                }"
                @wheel="onCardWheel"
              >
                <div
                  v-for="project in projects"
                  :key="project.pid"
                  class="relative flex h-[160px] w-[280px] min-w-[280px] flex-shrink-0 flex-col"
                >
                  <div
                    v-if="renamingKey === cardKey(project.pid)"
                    class="flex h-full flex-col justify-center rounded-2xl bg-white p-4 shadow-sm"
                  >
                    <div class="mb-3 text-xs text-[#6b7280]">重命名科目</div>
                    <RenameInline
                      :initial="project.projectname"
                      :submitting="renameSubmitting"
                      placeholder="新科目名称"
                      @submit="(name) => submitProjectRename(project, name)"
                      @cancel="cancelRename"
                    />
                  </div>
                  <button
                    v-else
                    class="flex h-full w-full flex-col justify-between rounded-2xl bg-white p-4 text-left shadow-sm transition-colors hover:bg-[#f9fafb]"
                    type="button"
                    @click="goToProject(project)"
                  >
                    <div>
                      <h3 class="mb-2 truncate pr-8 text-lg font-bold">{{ project.projectname }}</h3>
                      <p class="font-hans line-clamp-2 text-sm text-[#6b7280]">创建于 {{ formatDate(project.created_at) }}</p>
                    </div>
                    <div class="font-hans flex justify-between border-t border-[#d1d5db] pt-3 text-xs text-[#9ca3af]">
                      <span>进入查看会话</span>
                      <span>{{ formatDate(project.timestamp) }}</span>
                    </div>
                  </button>
                  <div
                    v-if="renamingKey !== cardKey(project.pid)"
                    class="absolute right-2 top-2"
                  >
                    <RowMenu
                      :open="openMenuKey === cardKey(project.pid)"
                      @toggle="toggleMenu(cardKey(project.pid))"
                      @close="closeMenu"
                      @rename="startRename(cardKey(project.pid))"
                      @delete="askDeleteProject(project)"
                    />
                  </div>
                </div>
              </div>
              <div v-else class="rounded-2xl bg-white px-6 py-10 text-center text-sm text-[#6b7280] shadow-sm">
                还没有科目，在下方输入以新建。
              </div>
            </div>

            <!-- 列表视图 -->
            <div v-else key="list" class="flex flex-col" style="max-height: calc(100vh - 220px)">
              <div class="no-scrollbar flex-1 overflow-y-auto">
                <TransitionGroup name="ov-item" tag="div" class="space-y-3 pb-4">
                  <div v-for="(project, i) in projects" :key="project.pid" :style="{ '--i': i }">
                    <div
                      v-if="renamingKey === cardKey(project.pid)"
                      class="rounded-2xl bg-white p-4 shadow-sm"
                    >
                      <div class="mb-2 text-xs text-[#6b7280]">重命名科目</div>
                      <RenameInline
                        :initial="project.projectname"
                        :submitting="renameSubmitting"
                        placeholder="新科目名称"
                        @submit="(name) => submitProjectRename(project, name)"
                        @cancel="cancelRename"
                      />
                    </div>
                    <div
                      v-else
                      role="button"
                      tabindex="0"
                      class="group flex w-full cursor-pointer items-center justify-between rounded-2xl bg-white p-4 text-left shadow-sm transition-colors hover:bg-[#f9fafb]"
                      @click="goToProject(project)"
                      @keydown.enter.prevent="goToProject(project)"
                    >
                      <div class="min-w-0 flex-1 pr-4">
                        <div class="font-hans truncate font-medium text-[#1f2937]">{{ project.projectname }}</div>
                        <div class="font-hans mt-1 truncate text-xs text-[#9ca3af]">创建于 {{ formatDate(project.created_at) }}</div>
                      </div>
                      <RowMenu
                        :open="openMenuKey === cardKey(project.pid)"
                        @toggle="toggleMenu(cardKey(project.pid))"
                        @close="closeMenu"
                        @rename="startRename(cardKey(project.pid))"
                        @delete="askDeleteProject(project)"
                      />
                    </div>
                  </div>
                </TransitionGroup>
              </div>
            </div>
          </Transition>
        </div>

        <!-- 箭头：独立 Transition，向下冲出页面，与列表进场同时发生 -->
        <Transition name="ov-arrow">
          <div v-if="!expanded && projects.length > 0" class="mt-5 flex flex-col items-center gap-1.5">
            <span class="text-xs text-[#9ca3af]">点击查看所有科目</span>
            <button
              type="button"
              class="flex items-center justify-center py-1 text-[#1f2937] transition-opacity hover:opacity-50"
              @click="expand()"
            >
              <svg class="h-5 w-16" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 64 20" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 4l28 12L60 4" />
              </svg>
            </button>
          </div>
        </Transition>
      </div>
    </div>

    <!-- 底部面板：绝对定位，不影响上方内容布局 -->
    <div class="absolute bottom-0 left-0 right-0 px-4 pb-4 md:px-6">
      <div class="mx-auto w-full max-w-3xl">
        <!-- 创建面板：同一元素的展开/收起变换 -->
        <div
          class="create-panel"
          :class="{ expanded: showCreatePanel }"
          @click="!showCreatePanel && openCreatePanel()"
        >
          <span class="create-placeholder">新建科目...</span>

          <div class="create-fields">
            <div class="create-fields-inner">
              <p v-if="errorMessage" class="mb-3 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
                {{ errorMessage }}
              </p>
              <input
                ref="nameInput"
                v-model="newProjectName"
                type="text"
                class="w-full border-none bg-transparent py-2 text-base font-medium text-[#1f2937] outline-none placeholder:text-[#9ca3af]"
                placeholder="科目名称"
                :disabled="creatingProject"
                @keydown.enter.prevent="handleCreateProject"
                @keydown.esc.prevent="closeCreatePanel"
                @click.stop
              />
              <div class="mx-2 border-t border-[#f3f4f6]" />
              <div class="relative">
                <textarea
                  v-model="newProjectDesc"
                  class="w-full resize-none border-none bg-transparent py-2 text-sm leading-relaxed text-[#374151] outline-none placeholder:text-[#9ca3af]"
                  :placeholder="`一句话描述这个科目（可选，${DESC_MAX} 字以内）`"
                  rows="2"
                  :maxlength="DESC_MAX"
                  :disabled="creatingProject"
                  @keydown.esc.prevent="closeCreatePanel"
                  @click.stop
                />
                <span class="absolute bottom-2 right-0 text-xs text-[#d1d5db]">{{ newProjectDesc.length }} / {{ DESC_MAX }}</span>
              </div>
              <div class="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  class="rounded-2xl px-4 py-2 text-sm text-[#6b7280] transition hover:bg-[#f3f4f6]"
                  :disabled="creatingProject"
                  @click.stop="closeCreatePanel"
                >
                  取消
                </button>
                <button
                  type="button"
                  class="flex h-9 items-center justify-center gap-1 rounded-2xl border border-transparent bg-[#1f2937] px-5 text-sm text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]"
                  :disabled="!newProjectName.trim() || creatingProject"
                  @click.stop="handleCreateProject"
                >
                  创建科目
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <ConfirmDialog
      v-if="confirmDelete"
      :title="'删除科目'"
      :message="`确定删除「${confirmDelete.name}」？该科目下的所有会话和消息会被一并删除，操作不可恢复。`"
      :error="deleteError"
      :submitting="deleteSubmitting"
      @confirm="performDelete"
      @cancel="cancelDelete"
    />
  </div>
</template>

<style scoped>
/* 卡片视图离场：原地淡出 */
.ov-swap-leave-active {
  transition: opacity 420ms ease;
}
.ov-swap-leave-to {
  opacity: 0;
}

/* 列表视图进场：从下方上移淡入 */
.ov-swap-enter-active {
  transition: opacity 280ms ease, transform 280ms ease;
}
.ov-swap-enter-from {
  opacity: 0;
  transform: translateY(22px);
}

/* 列表条目错开进场 */
.ov-item-enter-active {
  transition:
    opacity 260ms ease calc(var(--i, 0) * 40ms),
    transform 260ms ease calc(var(--i, 0) * 40ms);
}
.ov-item-enter-from {
  opacity: 0;
  transform: translateY(18px);
}

/* 卡片滚动区：左右渐变淡出，延伸部分模糊 */
.card-scroller {
  -webkit-mask-image: linear-gradient(
    to right,
    transparent 0,
    black 4%,
    black 96%,
    transparent 100%
  );
  mask-image: linear-gradient(
    to right,
    transparent 0,
    black 4%,
    black 96%,
    transparent 100%
  );
}

/* 箭头离场：向下冲出页面 */
.ov-arrow-leave-active {
  transition: opacity 320ms ease, transform 320ms cubic-bezier(0.4, 0, 1, 1);
  pointer-events: none;
}
.ov-arrow-leave-to {
  opacity: 0;
  transform: translateY(120px);
}

/* ── 创建面板：同一元素的展开/收起变换 ── */
.create-panel {
  position: relative;
  cursor: pointer;
  border-radius: 1.5rem;
  background: white;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  padding: 1rem;
  overflow: hidden;
  transition:
    transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1),
    margin-bottom 0.4s cubic-bezier(0.2, 0.8, 0.2, 1),
    box-shadow 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.create-panel.expanded {
  cursor: default;
  transform: translateY(-12px);
  margin-bottom: -12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.create-placeholder {
  display: block;
  color: #9ca3af;
  transition: opacity 0.25s ease;
  opacity: 1;
  position: relative;
  z-index: 1;
}

.create-panel.expanded .create-placeholder {
  opacity: 0;
  height: 0;
  overflow: hidden;
}

.create-fields {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
  position: relative;
  z-index: 1;
}

.create-panel.expanded .create-fields {
  grid-template-rows: 1fr;
}

.create-fields-inner {
  overflow: hidden;
  min-height: 0;
}

.create-panel.expanded .create-fields-inner input,
.create-panel.expanded .create-fields-inner textarea {
  animation: create-field-in 0.35s cubic-bezier(0.2, 0.8, 0.2, 1) backwards;
}

.create-panel.expanded .create-fields-inner input {
  animation-delay: 0.08s;
}

.create-panel.expanded .create-fields-inner textarea {
  animation-delay: 0.14s;
}

.create-panel.expanded .create-fields-inner .pt-2 {
  animation: create-field-in 0.35s cubic-bezier(0.2, 0.8, 0.2, 1) 0.2s backwards;
}

@keyframes create-field-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.create-panel:not(.expanded) .create-fields-inner > * {
  opacity: 0;
  transition: opacity 0.2s ease;
}
</style>
