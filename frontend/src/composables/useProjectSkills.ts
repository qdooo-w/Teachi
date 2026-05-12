// frontend/src/composables/useProjectSkills.ts
//
// 把「当前项目的技能列表」做成跨视图的共享响应式数据：
// - App.vue 的项目技能管理对话框关闭后调用 refresh(pid)
// - ChatView 通过 watch(pid) 自动拉取；页面关心的是 skills ref 的值变化
// 取代原本 window 事件总线 "teachi-project-skills-changed" 的实现，
// 让两边通过"共享状态"而不是"全局广播"通信。
import { ref, watch, type Ref } from 'vue'
import { listSkills, type SkillMeta } from '../skills'

const cache = ref(new Map<string, SkillMeta[]>())

// 每个 pid 的 in-flight 请求，防止并发重复拉取
const inflight = new Map<string, Promise<void>>()

async function fetchFor(pid: string): Promise<void> {
  const existing = inflight.get(pid)
  if (existing) return existing
  const task = (async () => {
    try {
      const skills = await listSkills({ kind: 'project', pid })
      cache.value.set(pid, skills)
    } catch {
      // 拉取失败时缓存空列表，避免 UI 停在未定义态
      cache.value.set(pid, [])
    } finally {
      inflight.delete(pid)
    }
  })()
  inflight.set(pid, task)
  return task
}

/**
 * 读取某项目的技能列表。返回的 skills 随 pidRef 变化自动重取；
 * refresh 用于强制重拉（例如对话框新增 / 删除 / 修改技能后）。
 */
export function useProjectSkills(pidRef: Ref<string | null | undefined>) {
  const skills = ref<SkillMeta[]>([])

  watch(
    () => pidRef.value,
    async (pid) => {
      if (!pid) {
        skills.value = []
        return
      }
      if (!cache.value.has(pid)) await fetchFor(pid)
      skills.value = cache.value.get(pid) ?? []
    },
    { immediate: true },
  )

  async function refresh(): Promise<void> {
    const pid = pidRef.value
    if (!pid) return
    cache.value.delete(pid)
    inflight.delete(pid)
    await fetchFor(pid)
    skills.value = cache.value.get(pid) ?? []
  }

  return { skills, refresh }
}
