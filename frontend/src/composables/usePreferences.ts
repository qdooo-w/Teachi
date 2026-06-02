import { ref } from 'vue'
import { getPreferences, updatePreferences } from '../api'

export type EnterMode = 'enter' | 'ctrl_enter'

/**
 * 用户偏好的模块级单例：
 * 发送快捷键偏好（enter_mode）需跨视图共享——设置中心（SettingsDialog）修改后，
 * 已挂载的 ChatView Composer 必须实时生效。若各视图各自持有一份局部 ref，
 * 改了设置但聊天页不更新，就会表现为「偏好设置失效」。
 *
 * 与 useProjects / useProjectSkills 一致：状态用模块级 ref 持有，所有调用方共享同一引用。
 */
const enterMode = ref<EnterMode>('enter')
let loaded = false
let loadingPromise: Promise<void> | null = null

/** 从后端加载偏好（带去重）。force=true 时强制重新拉取。 */
async function loadEnterMode(force = false): Promise<void> {
  if (loaded && !force) return
  if (loadingPromise) return loadingPromise
  loadingPromise = (async () => {
    try {
      const prefs = await getPreferences()
      enterMode.value = (prefs.enter_mode as EnterMode) || 'enter'
      loaded = true
    } finally {
      loadingPromise = null
    }
  })()
  return loadingPromise
}

/** 保存偏好到后端并更新共享状态，使所有订阅方（如 Composer）立即响应。 */
async function saveEnterMode(mode: EnterMode): Promise<void> {
  const prefs = await updatePreferences({ enter_mode: mode })
  enterMode.value = (prefs.enter_mode as EnterMode) || mode
  loaded = true
}

/** 外部直接同步共享状态（例如设置中心已自行拉取后回填）。 */
function setEnterMode(mode: EnterMode): void {
  enterMode.value = mode
  loaded = true
}

export function usePreferences() {
  return { enterMode, loadEnterMode, saveEnterMode, setEnterMode }
}
