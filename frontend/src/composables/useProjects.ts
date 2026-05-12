// frontend/src/composables/useProjects.ts
import { ref } from 'vue'
import {
  listProjects,
  type ProjectItem,
  getCurrentUserId,
} from '../api'

const projects = ref<ProjectItem[]>([])

// 多个视图（Subject / Chat / App.vue 的 setOnTokenReady）可能同时触发 loadProjects。
// 缓存 in-flight Promise，确保并发调用只走一次网络。
let inflight: Promise<void> | null = null

async function loadProjects(): Promise<void> {
  if (inflight) return inflight
  const userId = getCurrentUserId()
  if (!userId) return
  inflight = (async () => {
    try {
      projects.value = await listProjects(userId)
    } finally {
      inflight = null
    }
  })()
  return inflight
}

function upsertProject(project: ProjectItem): void {
  const idx = projects.value.findIndex((p) => p.pid === project.pid)
  if (idx === -1) projects.value = [project, ...projects.value]
  else projects.value = projects.value.map((p) => (p.pid === project.pid ? project : p))
}

function removeProject(pid: string): void {
  projects.value = projects.value.filter((p) => p.pid !== pid)
}

function prependProject(project: ProjectItem): void {
  projects.value = [project, ...projects.value]
}

function resetProjects(): void {
  projects.value = []
}

export function useProjects() {
  return { projects, loadProjects, upsertProject, removeProject, prependProject, resetProjects }
}
