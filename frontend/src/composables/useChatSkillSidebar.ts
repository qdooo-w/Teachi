// frontend/src/composables/useChatSkillSidebar.ts
//
// 会话界面技能侧边栏 + 内联编辑器状态管理（模块级单例）
// - App.vue header 的箭头按钮切换 chatSidebarOpen
// - ChatSkillSidebar 读取 skills 列表，点击技能设置 editingSkill
// - ChatView 读取 editingSkill，非 null 时渲染 SkillEditorPanel
import { ref } from 'vue'
import type { FileSpace } from '../skills'

/** 侧边栏开关 */
const chatSidebarOpen = ref(false)

/** 当前正在内联编辑的技能（null = 显示聊天） */
const editingSkill = ref<{
  space: FileSpace
  name: string
  displayName: string
} | null>(null)

export function useChatSkillSidebar() {
  function toggleSidebar(): void {
    chatSidebarOpen.value = !chatSidebarOpen.value
  }

  function closeSidebar(): void {
    chatSidebarOpen.value = false
  }

  function openEditor(space: FileSpace, name: string, displayName: string): void {
    editingSkill.value = { space, name, displayName }
  }

  function closeEditor(): void {
    editingSkill.value = null
  }

  return {
    chatSidebarOpen,
    editingSkill,
    toggleSidebar,
    closeSidebar,
    openEditor,
    closeEditor,
  }
}
