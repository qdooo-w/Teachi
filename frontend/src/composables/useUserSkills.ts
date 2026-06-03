// frontend/src/composables/useUserSkills.ts
//
// 把「当前用户的技能列表」做成跨视图的共享响应式数据：
// - App.vue 在关闭技能管理对话框时调用 refresh()
// - ChatView 通过 load() 自动拉取
import { ref } from 'vue'
import { listSkills, type SkillMeta } from '../skills'
import { getCurrentUserId } from '../api'

const skills = ref<SkillMeta[]>([])
const loadedUserId = ref<string | null>(null)
let inflight: Promise<void> | null = null

async function fetchUserSkills(userId: string): Promise<void> {
  if (inflight) return inflight
  inflight = (async () => {
    try {
      const result = await listSkills({ kind: 'user', userId })
      skills.value = result
      loadedUserId.value = userId
    } catch {
      // 失败时清空以防状态错误
      skills.value = []
      loadedUserId.value = null
    } finally {
      inflight = null
    }
  })()
  return inflight
}

export function useUserSkills() {
  async function load(): Promise<void> {
    const userId = getCurrentUserId()
    if (!userId) {
      skills.value = []
      loadedUserId.value = null
      return
    }
    if (loadedUserId.value !== userId) {
      await fetchUserSkills(userId)
    }
  }

  async function refresh(): Promise<void> {
    const userId = getCurrentUserId()
    if (!userId) return
    loadedUserId.value = null
    await fetchUserSkills(userId)
  }

  return {
    skills,
    load,
    refresh
  }
}
