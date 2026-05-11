// frontend/src/composables/useProjects.ts
import { ref } from 'vue'
import {
  listProjects,
  type ProjectItem,
  getCurrentUserId,
} from '../api'

const projects = ref<ProjectItem[]>([])

async function loadProjects(): Promise<void> {
  const userId = getCurrentUserId()
  if (!userId) return
  projects.value = await listProjects(userId)
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
