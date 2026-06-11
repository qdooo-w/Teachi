<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useChatSkillSidebar } from '../composables/useChatSkillSidebar'
import { useProjectSkills } from '../composables/useProjectSkills'
import { useUserSkills } from '../composables/useUserSkills'
import { useNotification } from '../composables/useNotification'
import { getCurrentUserId, getErrorMessage } from '../api'
import { deleteSkill, type SkillMeta } from '../skills'
import { confirmDanger } from '../composables/useConfirmDialog'

const route = useRoute()
const { chatSidebarOpen, openEditor } = useChatSkillSidebar()

// ── 技能数据 ────────────────────────────────────────────────────────────────
const pid = computed(() => (route.params.pid as string) || null)

const { showSuccess, showError } = useNotification()
const deletingSkillName = ref<string | null>(null)

// 用户级技能
const { skills: userSkills, load: loadUserSkills, refresh: refreshUserSkills } = useUserSkills()

// 项目级技能
const { skills: projectSkills, refresh: refreshProjectSkills } = useProjectSkills(pid)

// ── 折叠状态（默认收起） ────────────────────────────────────────────────────
const userExpanded = ref(false)
const projectExpanded = ref(false)

const hasUserSkills = computed(() => userSkills.value.length > 0)
const hasProjectSkills = computed(() => projectSkills.value.length > 0)

// ── 生命周期 ────────────────────────────────────────────────────────────────
onMounted(() => {
  void loadUserSkills()
})


function selectSkill(kind: 'user' | 'project', skill: SkillMeta): void {
  const userId = getCurrentUserId()
  if (kind === 'user' && userId) {
    openEditor({ kind: 'user', userId }, skill.name, skill.display_name || skill.name)
  } else if (kind === 'project' && pid.value) {
    openEditor({ kind: 'project', pid: pid.value }, skill.name, skill.display_name || skill.name)
  }
}

async function handleDeleteSkill(kind: 'user' | 'project', skill: SkillMeta): Promise<void> {
  const skillName = skill.name
  const displayName = skill.display_name || skill.name
  const confirmed = await confirmDanger({
    title: '删除技能',
    message: `确定要彻底删除技能「${displayName}」吗？此操作不可恢复。`,
    confirmText: '删除',
  })
  if (!confirmed) return

  const userId = getCurrentUserId()
  let space: any = null
  if (kind === 'user' && userId) {
    space = { kind: 'user', userId }
  } else if (kind === 'project' && pid.value) {
    space = { kind: 'project', pid: pid.value }
  }

  if (!space) return

  deletingSkillName.value = skill.name
  try {
    await deleteSkill(space, skillName)
    showSuccess(`已成功删除技能「${displayName}」`)

    // 刷新列表
    if (kind === 'user') {
      await refreshUserSkills()
    } else {
      await refreshProjectSkills()
    }
  } catch (e) {
    showError(`删除技能失败: ${getErrorMessage(e)}`)
  } finally {
    deletingSkillName.value = null
  }
}
</script>

<template>
  <!-- 侧边栏主体（与主侧边栏同宽 w-56 / 224px） -->
  <aside
    :class="[
      'flex flex-shrink-0 flex-col bg-white border-l border-[#e5e7eb] transition-all duration-300 overflow-hidden',
      chatSidebarOpen ? 'w-56' : 'w-0',
    ]"
  >
    <!-- 内容区：宽度过渡期间隐藏，展开到位后再淡入；收起时先淡出再收缩 -->
    <div
      :class="[
        'flex h-full w-56 flex-shrink-0 flex-col',
        'transition-opacity duration-150',
        chatSidebarOpen ? 'opacity-100 delay-100' : 'opacity-0',
      ]"
    >
    <!-- 标题栏 -->
    <div class="flex h-14 flex-shrink-0 items-center px-4 border-b border-[#e5e7eb]">
      <span
        :class="[
          'text-sm font-semibold text-[#1f2937] font-hans whitespace-nowrap transition-opacity duration-200',
          chatSidebarOpen ? 'opacity-100 delay-200' : 'opacity-0 delay-0',
        ]"
      >
        技能管理
      </span>
    </div>

    <!-- 技能列表区（内边距与主侧边栏统一 px-2.5 py-4） -->
    <div class="flex-1 overflow-y-auto px-2.5 py-3 space-y-1 font-hans whitespace-nowrap">
      <!-- 用户级技能 -->
      <div>
        <button
          class="flex h-8 w-full items-center justify-start gap-1.5 rounded-xl pl-4 pr-2 text-left text-xs font-medium text-[#6b7280] hover:bg-[#f3f4f6] transition-colors active:scale-95"
          type="button"
          @click="userExpanded = !userExpanded"
        >
          <svg
            :class="['h-3 w-3 flex-shrink-0 text-[#9ca3af] transition-transform duration-200', userExpanded ? 'rotate-90' : '']"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
          <span>用户级技能</span>
          <span class="ml-auto text-[10px] text-[#9ca3af]">{{ userSkills.length }}</span>
        </button>
        <div
          :class="[
            'overflow-hidden transition-[max-height] duration-300 ease-out',
            userExpanded ? 'max-h-[500px]' : 'max-h-0',
          ]"
        >
          <div class="mt-0.5 space-y-0.5">
            <div
              v-if="!hasUserSkills"
              class="px-4 py-1.5 text-xs text-[#9ca3af]"
            >
              暂无用户级技能
            </div>
            <div
              v-for="skill in userSkills"
              :key="'user-' + skill.name"
              role="button"
              tabindex="0"
              :class="[
                'group relative flex h-8 mx-1 cursor-pointer items-center justify-start gap-2 rounded-xl pl-4 pr-8 text-left transition-colors',
                'text-[13px]',
                'hover:bg-[#e5e7eb]',
              ]"
              @click="selectSkill('user', skill)"
              @keydown.enter.prevent="selectSkill('user', skill)"
            >
              <svg class="h-3.5 w-3.5 flex-shrink-0 text-[#9ca3af]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              <span class="font-hans flex-1 truncate">{{ skill.display_name || skill.name }}</span>
              <!-- 删除技能按钮 -->
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 flex h-5.5 w-5.5 items-center justify-center rounded-lg text-gray-400 opacity-0 group-hover:opacity-100 hover:bg-[#d1d5db] hover:text-red-600 transition-all active:scale-90"
                title="删除技能"
                @click.stop="handleDeleteSkill('user', skill)"
              >
                <!-- Loading 状态 -->
                <span v-if="deletingSkillName === skill.name" class="h-3.5 w-3.5 border-2 border-red-600/30 border-t-red-600 rounded-full animate-spin" />
                <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 分隔线 -->
      <div class="my-2 border-t border-[#e5e7eb]/60" />

      <!-- 项目级技能 -->
      <div>
        <button
          class="flex h-8 w-full items-center justify-start gap-1.5 rounded-xl pl-4 pr-2 text-left text-xs font-medium text-[#6b7280] hover:bg-[#f3f4f6] transition-colors active:scale-95"
          type="button"
          @click="projectExpanded = !projectExpanded"
        >
          <svg
            :class="['h-3 w-3 flex-shrink-0 text-[#9ca3af] transition-transform duration-200', projectExpanded ? 'rotate-90' : '']"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
          <span>项目级技能</span>
          <span class="ml-auto text-[10px] text-[#9ca3af]">{{ projectSkills.length }}</span>
        </button>
        <div
          :class="[
            'overflow-hidden transition-[max-height] duration-300 ease-out',
            projectExpanded ? 'max-h-[500px]' : 'max-h-0',
          ]"
        >
          <div class="mt-0.5 space-y-0.5">
            <div
              v-if="!hasProjectSkills"
              class="px-4 py-1.5 text-xs text-[#9ca3af]"
            >
              暂无项目级技能
            </div>
            <div
              v-for="skill in projectSkills"
              :key="'project-' + skill.name"
              role="button"
              tabindex="0"
              :class="[
                'group relative flex h-8 mx-1 cursor-pointer items-center justify-start gap-2 rounded-xl pl-4 pr-8 text-left transition-colors',
                'text-[13px]',
                'hover:bg-[#e5e7eb]',
              ]"
              @click="selectSkill('project', skill)"
              @keydown.enter.prevent="selectSkill('project', skill)"
            >
              <svg class="h-3.5 w-3.5 flex-shrink-0 text-[#9ca3af]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              <span class="font-hans flex-1 truncate">{{ skill.display_name || skill.name }}</span>
              <!-- 删除技能按钮 -->
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 flex h-5.5 w-5.5 items-center justify-center rounded-lg text-gray-400 opacity-0 group-hover:opacity-100 hover:bg-[#d1d5db] hover:text-red-600 transition-all active:scale-90"
                title="删除技能"
                @click.stop="handleDeleteSkill('project', skill)"
              >
                <!-- Loading 状态 -->
                <span v-if="deletingSkillName === skill.name" class="h-3.5 w-3.5 border-2 border-red-600/30 border-t-red-600 rounded-full animate-spin" />
                <svg v-else class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>
  </aside>
</template>
