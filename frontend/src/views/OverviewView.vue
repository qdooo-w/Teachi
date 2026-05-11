<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

const router = useRouter()
const { projects, loadProjects, prependProject, upsertProject, removeProject } = useProjects()
const { closeSidebarOnMobile } = useLayout()

const newProjectName = ref('')
const creatingProject = ref(false)
const errorMessage = ref('')

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

async function handleCreateProject(): Promise<void> {
  const name = newProjectName.value.trim()
  if (!name || creatingProject.value) return
  const userId = getCurrentUserId()
  if (!userId) return

  creatingProject.value = true
  errorMessage.value = ''
  try {
    const project = await createProject(userId, name)
    newProjectName.value = ''
    prependProject(project)
    await goToProject(project)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    creatingProject.value = false
  }
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

onMounted(() => {
  if (projects.value.length === 0) void loadProjects()
})
</script>

<template>
  <div class="absolute inset-0 flex flex-col overflow-y-auto px-4 py-5 md:px-6">
    <div class="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center">
      <h1 class="mb-10 text-4xl font-bold tracking-tight md:text-5xl">科目总览</h1>
      <div
        v-if="projects.length > 0"
        class="no-scrollbar -mx-4 flex gap-4 overflow-x-auto px-4 pb-2 md:-mx-6 md:px-6"
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
              <p class="line-clamp-2 text-sm text-[#6b7280]">创建于 {{ formatDate(project.created_at) }}</p>
            </div>
            <div class="flex justify-between border-t border-[#d1d5db] pt-3 text-xs text-[#9ca3af]">
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

    <div class="mx-auto w-full max-w-3xl pb-2">
      <p v-if="errorMessage" class="mb-2 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
        {{ errorMessage }}
      </p>
      <div class="relative flex flex-col gap-3 rounded-3xl bg-white p-4 shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-[#1f6f5b]/20">
        <textarea
          v-model="newProjectName"
          class="min-h-[24px] w-full resize-none overflow-y-auto border-none bg-transparent leading-normal text-[#1f2937] outline-none placeholder:text-[#9ca3af]"
          placeholder="新建科目：输入科目名称..."
          rows="1"
          :disabled="creatingProject"
          @keydown.enter.prevent="handleCreateProject"
        />
        <div class="flex items-center justify-end">
          <button
            type="button"
            class="flex h-9 items-center justify-center gap-1 rounded-2xl border border-transparent bg-[#1f2937] px-5 text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]"
            :disabled="!newProjectName.trim() || creatingProject"
            title="创建科目"
            @click="handleCreateProject"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14m0 0-6-6m6 6-6 6" />
            </svg>
          </button>
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
