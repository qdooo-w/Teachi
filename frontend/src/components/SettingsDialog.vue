<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  type ModelConfigItem,
  type UpdateModelConfigRequest,
  type TestConnectionResponse,
  type AccountInfo,
  type Preferences,
  listModelConfigs,
  createModelConfig,
  updateModelConfig,
  activateModelConfig,
  deactivateAllModelConfigs,
  deleteModelConfig,
  testConnectionWithParams,
  testConnectionWithConfig,
  fetchModels,
  getAccountInfo,
  updateUsername,
  changePassword,
  getPreferences,
  updatePreferences,
  getErrorMessage,
} from '../api'
import { usePreferences } from '../composables/usePreferences'

const emit = defineEmits<{
  close: []
}>()

type TabName = 'model' | 'account' | 'preferences'
const activeTab = ref<TabName>('model')
const tabs: { key: TabName; label: string }[] = [
  { key: 'model', label: '模型配置' },
  { key: 'account', label: '账号设置' },
  { key: 'preferences', label: '偏好设置' },
]

const configs = ref<ModelConfigItem[]>([])
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const testing = ref(false)
const fetchingModels = ref(false)
const availableModels = ref<string[]>([])
const showModelDropdown = ref(false)
const modelDropdownIndex = ref(-1)
const modelDropdownEl = ref<HTMLElement | null>(null)
const modelListCache = ref<Map<string, string[]>>(new Map())
const errorMsg = ref('')
const testResult = ref<TestConnectionResponse | null>(null)
const editingId = ref<string | null>(null)
const isCreating = computed(() => editingId.value === 'create')

const testPassed = ref(false)
const isInitializing = ref(false)
const formSnapshot = ref<any>(null)

/** 逐字段对照快照：JSON.stringify 在 Vue reactive proxy 上不可靠，改用显式 diff */
function isFormDirty(): boolean {
  if (!formSnapshot.value) return false
  const s = formSnapshot.value as Record<string, unknown>
  const f = form.value as unknown as Record<string, unknown>
  const keys = ['config_name', 'api_key', 'base_url', 'model_name', 'user_instruction', 'temperature', 'max_tokens', 'supports_vision']
  return keys.some((k) => f[k] !== s[k])
}

const isModelFormDirty = computed(() => isFormDirty())

const form = ref({
  config_name: '',
  api_key: '',
  base_url: '',
  model_name: '',
  user_instruction: '',
  temperature: null as number | null,
  max_tokens: null as number | null,
  supports_vision: false,
})
const showAdvanced = ref(false)
const showApiKey = ref(false)
const apiKeyIsMasked = ref(false)
const confirmDeleteId = ref<string | null>(null)
const confirmDeleteName = ref('')
const canSave = computed(() => form.value.config_name.trim().length > 0)

// 视觉模型帮助 tooltip：用 Teleport 渲染到 body，避开所有 overflow 裁剪
const visionTooltipTrigger = ref<HTMLElement | null>(null)
const showVisionTooltip = ref(false)
const visionTooltipPos = ref({ top: 0, left: 0 })
function showVisionTooltipFn(): void {
  const el = visionTooltipTrigger.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  visionTooltipPos.value = { top: rect.bottom + 6, left: rect.left }
  showVisionTooltip.value = true
}
function hideVisionTooltipFn(): void { showVisionTooltip.value = false }

watch(
  () => [form.value.api_key, form.value.base_url, form.value.model_name, form.value.supports_vision],
  () => {
    if (isInitializing.value) return
    testPassed.value = false
    testResult.value = null
  }
)

async function loadConfigs(): Promise<void> {
  loading.value = true; errorMsg.value = ''
  try { configs.value = await listModelConfigs() }
  catch (e) { errorMsg.value = getErrorMessage(e) }
  finally { loading.value = false }
}

function startCreate(): void {
  isInitializing.value = true
  editingId.value = 'create'
  form.value = { config_name: '', api_key: '', base_url: '', model_name: '', user_instruction: '', temperature: null, max_tokens: null, supports_vision: false }
  showAdvanced.value = false; showApiKey.value = false; apiKeyIsMasked.value = false; testResult.value = null; errorMsg.value = ''
  testPassed.value = false
  formSnapshot.value = JSON.parse(JSON.stringify(form.value))
  setTimeout(() => {
    isInitializing.value = false
  }, 0)
}

function startEdit(config: ModelConfigItem): void {
  isInitializing.value = true
  editingId.value = config.config_id
  form.value = { config_name: config.config_name, api_key: config.api_key, base_url: config.base_url, model_name: config.model_name, user_instruction: config.user_instruction || '', temperature: config.temperature, max_tokens: config.max_tokens, supports_vision: !!config.supports_vision }
  showAdvanced.value = !!(config.temperature || config.max_tokens || config.user_instruction)
  showApiKey.value = false; apiKeyIsMasked.value = config.api_key.startsWith('*'); testResult.value = null; errorMsg.value = ''
  testPassed.value = true
  formSnapshot.value = JSON.parse(JSON.stringify(form.value))
  setTimeout(() => {
    isInitializing.value = false
  }, 0)
}


async function save(): Promise<void> {
  saving.value = true; errorMsg.value = ''
  try {
    if (isCreating.value) {
      await createModelConfig({ config_name: form.value.config_name.trim(), api_key: form.value.api_key, base_url: form.value.base_url, model_name: form.value.model_name, user_instruction: form.value.user_instruction, temperature: form.value.temperature, max_tokens: form.value.max_tokens, supports_vision: form.value.supports_vision, is_active: false })
    } else if (editingId.value) {
      const payload: UpdateModelConfigRequest = { config_name: form.value.config_name.trim(), ...(apiKeyIsMasked.value ? {} : { api_key: form.value.api_key }), base_url: form.value.base_url, model_name: form.value.model_name, user_instruction: form.value.user_instruction, temperature: form.value.temperature, max_tokens: form.value.max_tokens, supports_vision: form.value.supports_vision }
      await updateModelConfig(editingId.value, payload)
    }
    editingId.value = null; await loadConfigs()
  } catch (e) { errorMsg.value = getErrorMessage(e) }
  finally { saving.value = false }
}




async function handleActivate(config: ModelConfigItem): Promise<void> {
  try { if (config.is_active) { await deactivateAllModelConfigs() } else { await activateModelConfig(config.config_id) }; await loadConfigs() }
  catch (e) { errorMsg.value = getErrorMessage(e) }
}

function requestDelete(config: ModelConfigItem): void { confirmDeleteId.value = config.config_id; confirmDeleteName.value = config.config_name }
function cancelDelete(): void { confirmDeleteId.value = null; confirmDeleteName.value = '' }

async function performDelete(): Promise<void> {
  if (!confirmDeleteId.value) return
  deleting.value = true
  try { await deleteModelConfig(confirmDeleteId.value); if (editingId.value === confirmDeleteId.value) editingId.value = null; await loadConfigs(); confirmDeleteId.value = null }
  catch (e) { errorMsg.value = getErrorMessage(e) }
  finally { deleting.value = false }
}

async function testConnection(): Promise<void> {
  testing.value = true; errorMsg.value = ''; testResult.value = null
  try {
    if (editingId.value && apiKeyIsMasked.value) { testResult.value = await testConnectionWithConfig(editingId.value) }
    else { testResult.value = await testConnectionWithParams({ api_key: form.value.api_key, base_url: form.value.base_url, model_name: form.value.model_name, supports_vision: form.value.supports_vision }) }
    testPassed.value = !!testResult.value.success
  } catch (e) {
    testResult.value = { success: false, message: getErrorMessage(e), model: null }
    testPassed.value = false
  }
  finally { testing.value = false }
}

async function fetchModelList(): Promise<void> {
  const apiKey = form.value.api_key
  const baseUrl = form.value.base_url
  if (!apiKey || apiKey.startsWith('*')) {
    errorMsg.value = '请先填写 API Key'
    return
  }
  if (!baseUrl) {
    errorMsg.value = '请先填写 Base URL'
    return
  }

  const cacheKey = `${apiKey}|${baseUrl}`
  if (modelListCache.value.has(cacheKey)) {
    availableModels.value = modelListCache.value.get(cacheKey)!
    showModelDropdown.value = true
    return
  }

  fetchingModels.value = true; errorMsg.value = ''
  try {
    const result = await fetchModels({ api_key: apiKey, base_url: baseUrl })
    if (result.success) {
      if (result.models.length === 0) {
        errorMsg.value = '该提供商返回了空的模型列表'
      } else {
        availableModels.value = result.models
        modelListCache.value.set(cacheKey, result.models)
        showModelDropdown.value = true
      }
    } else {
      errorMsg.value = result.message || '获取模型列表失败'
    }
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally { fetchingModels.value = false }
}

function selectModel(name: string): void {
  form.value.model_name = name
  showModelDropdown.value = false
}

function handleModelDropdownKeydown(e: KeyboardEvent): void {
  if (!showModelDropdown.value || availableModels.value.length === 0) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    modelDropdownIndex.value = Math.min(modelDropdownIndex.value + 1, availableModels.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    modelDropdownIndex.value = Math.max(modelDropdownIndex.value - 1, 0)
  } else if (e.key === 'Enter' && modelDropdownIndex.value >= 0) {
    e.preventDefault()
    selectModel(availableModels.value[modelDropdownIndex.value])
  } else if (e.key === 'Escape') {
    showModelDropdown.value = false
  }
}

function handleModelDropdownMousedown(e: MouseEvent): void {
  if (modelDropdownEl.value && !modelDropdownEl.value.contains(e.target as Node)) {
    showModelDropdown.value = false
  }
}

watch(showModelDropdown, (open) => {
  if (open) {
    document.addEventListener('mousedown', handleModelDropdownMousedown, true)
  } else {
    document.removeEventListener('mousedown', handleModelDropdownMousedown, true)
    modelDropdownIndex.value = -1
  }
})

watch(
  () => [form.value.api_key, form.value.base_url],
  () => {
    if (isInitializing.value) return
    availableModels.value = []
    showModelDropdown.value = false
  }
)

const accountInfo = ref<AccountInfo | null>(null)
const accountLoading = ref(false)
const usernameForm = ref({ username: '' })
const passwordForm = ref({ current_password: '', new_password: '', confirm_password: '' })
const usernameSaving = ref(false)
const passwordSaving = ref(false)
const usernameMsg = ref('')
const passwordMsg = ref('')

const isUsernameDirty = computed(() => {
  return accountInfo.value ? usernameForm.value.username.trim() !== accountInfo.value.username.trim() : false
})

const isPasswordDirty = computed(() => {
  return !!(passwordForm.value.current_password && passwordForm.value.new_password && passwordForm.value.confirm_password)
})

async function loadAccountInfo(): Promise<void> {
  accountLoading.value = true
  try { accountInfo.value = await getAccountInfo(); usernameForm.value.username = accountInfo.value.username }
  catch (e) { /* ignore */ }
  finally { accountLoading.value = false }
}

async function saveUsername(): Promise<void> {
  usernameSaving.value = true; usernameMsg.value = ''
  try { accountInfo.value = await updateUsername({ username: usernameForm.value.username.trim() }); usernameMsg.value = '用户名已更新' }
  catch (e) { usernameMsg.value = getErrorMessage(e) }
  finally { usernameSaving.value = false }
}

async function savePassword(): Promise<void> {
  if (passwordForm.value.new_password !== passwordForm.value.confirm_password) { passwordMsg.value = '两次输入的新密码不一致'; return }
  passwordSaving.value = true; passwordMsg.value = ''
  try { await changePassword({ current_password: passwordForm.value.current_password, new_password: passwordForm.value.new_password }); passwordForm.value = { current_password: '', new_password: '', confirm_password: '' }; passwordMsg.value = '密码已更新' }
  catch (e) { passwordMsg.value = getErrorMessage(e) }
  finally { passwordSaving.value = false }
}

const { setEnterMode } = usePreferences()

const prefs = ref<Preferences>({ enter_mode: 'enter', updated_at: null })
const prefsLoading = ref(false)
const prefsSaving = ref(false)
const prefsMsg = ref('')
const initialEnterMode = ref<string>('enter')

const isPrefsDirty = computed(() => {
  return prefs.value.enter_mode !== initialEnterMode.value
})

async function loadPreferences(): Promise<void> {
  prefsLoading.value = true
  try {
    prefs.value = await getPreferences()
    initialEnterMode.value = prefs.value.enter_mode
    // 同步到共享 composable，确保已挂载的 ChatView 实时感知当前偏好
    setEnterMode((prefs.value.enter_mode as 'enter' | 'ctrl_enter') || 'enter')
  }
  catch (e) { /* ignore */ }
  finally { prefsLoading.value = false }
}

async function savePreferences(): Promise<void> {
  prefsSaving.value = true; prefsMsg.value = ''
  try {
    prefs.value = await updatePreferences({ enter_mode: prefs.value.enter_mode })
    initialEnterMode.value = prefs.value.enter_mode
    // 推送到共享 composable，ChatView Composer 实时切换发送快捷键
    setEnterMode((prefs.value.enter_mode as 'enter' | 'ctrl_enter') || 'enter')
    prefsMsg.value = '偏好已保存'
  }
  catch (e) { prefsMsg.value = getErrorMessage(e) }
  finally { prefsSaving.value = false }
}

onMounted(() => { loadConfigs(); loadAccountInfo(); loadPreferences() })
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
    <div class="modal-card relative flex h-[560px] w-[640px] flex-col rounded-2xl bg-white overflow-hidden font-hans">
      <!-- Tab 栏（顶部标题栏：浅灰底 + 底部细分隔线，与卡片圆角衔接） -->
      <div class="flex px-5 pt-3 relative rounded-t-2xl bg-[#f9fafb] border-b border-[#eef0f2]">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="relative px-4 pb-2.5 text-sm font-medium transition-colors"
          :class="activeTab === tab.key ? 'text-[#1f2937]' : 'text-[#9ca3af] hover:text-[#6b7280]'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span v-if="activeTab === tab.key" class="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-[#1f2937]" />
        </button>
        <button
          type="button"
          class="absolute top-3 right-4 text-[#9ca3af] hover:text-[#6b7280] transition-colors"
          @click="emit('close')"
        >
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- 模型配置 Tab -->
      <div v-if="activeTab === 'model'" class="flex flex-1 overflow-hidden">
        <!-- 左侧列表：独立的 overflow-hidden + 左下圆角，防止背景色渗透到卡片外部 -->
        <div class="w-56 flex-shrink-0 overflow-y-auto rounded-bl-2xl bg-[#f9fafb] p-3">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-xs font-medium text-[#6b7280]">配置列表</span>
            <button class="text-xs text-[#1f2937] hover:text-[#111827]" @click="startCreate">+ 新增</button>
          </div>
          <div v-if="loading" class="py-4 text-center text-xs text-[#9ca3af]">加载中...</div>
          <div v-else-if="configs.length === 0" class="py-4 text-center text-xs text-[#9ca3af]">暂无配置</div>
          <div v-for="config in configs" :key="config.config_id" class="group relative">
            <div class="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm transition-colors cursor-pointer" :class="editingId === config.config_id ? 'bg-[#f3f4f6] text-[#1f2937]' : 'text-[#374151] hover:bg-[#f9fafb]'" @click="startEdit(config)">
              <span class="inline-block h-2 w-2 flex-shrink-0 rounded-full cursor-pointer" :class="config.is_active ? 'bg-emerald-500' : 'bg-[#d1d5db]'" :title="config.is_active ? '取消激活' : '设为激活'" @click.stop="handleActivate(config)" />
              <span class="truncate">{{ config.config_name }}</span>
            </div>
            <button v-if="editingId === config.config_id" class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-[#9ca3af] opacity-0 transition hover:text-red-500 group-hover:opacity-100" title="删除" @click.stop="requestDelete(config)">
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
        <!-- 右侧：相对定位容器（浮动保存按钮的锚点），内层独立滚动避免裁剪 tooltip -->
        <div class="relative flex-1">
          <div class="h-full overflow-y-auto p-5">
            <div v-if="errorMsg" class="mb-3 rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{{ errorMsg }}</div>
            <template v-if="editingId === null">
              <div class="flex flex-col items-center justify-center py-12 text-center">
                <svg class="mb-3 h-10 w-10 text-[#d1d5db]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                <p class="mb-1 text-sm font-medium text-[#374151]">模型配置</p>
                <p class="text-xs text-[#9ca3af]">选择左侧配置编辑，或新增一个</p>
              </div>
            </template>
            <template v-else>
              <div class="space-y-3">
                <label class="block">
                  <span class="mb-1 block text-sm font-medium text-[#374151]">配置名称 <span class="text-red-500">*</span></span>
                  <input v-model="form.config_name" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="例如：GPT-4o" />
                </label>
                <label class="block">
                  <div class="mb-1 flex items-center justify-between">
                    <span class="text-sm font-medium text-[#374151]">API Key</span>
                    <button type="button" class="text-xs text-[#6b7280] hover:text-[#1f2937]" @click="showApiKey = !showApiKey">{{ showApiKey ? '隐藏' : '显示' }}</button>
                  </div>
                  <input v-model="form.api_key" :type="showApiKey ? 'text' : 'password'" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="sk-..." />
                </label>
                <label class="block">
                  <span class="mb-1 block text-sm font-medium text-[#374151]">Base URL</span>
                  <input v-model="form.base_url" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="https://api.openai.com/v1" />
                </label>
                <label class="block">
                  <div class="mb-1 flex items-center gap-2">
                    <span class="text-sm font-medium text-[#374151]">模型名称</span>
                    <!-- 视觉模型帮助提示（trigger + body Teleport，不受 overflow 裁剪） -->
                    <span ref="visionTooltipTrigger" class="flex h-4 w-4 cursor-help items-center justify-center rounded-full bg-[#e5e7eb] text-[10px] font-bold text-[#6b7280]" @mouseenter="showVisionTooltipFn" @mouseleave="hideVisionTooltipFn">?</span>
                    <!-- 获取模型列表按钮 -->
                    <button
                      type="button"
                      class="flex items-center gap-1 text-[11px] text-[#6b7280] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:text-[#d1d5db]"
                      :disabled="fetchingModels || !form.api_key || form.api_key.startsWith('*') || !form.base_url"
                      @click="fetchModelList"
                    >
                      <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                      {{ fetchingModels ? '获取中...' : '获取列表' }}
                    </button>
                    <!-- 视觉模型开关（摇杆） -->
                    <label class="ml-auto flex cursor-pointer items-center gap-2 select-none" title="开启后，此配置可作为视觉模型用于图片理解">
                      <span class="text-[11px] text-[#9ca3af]">视觉</span>
                      <div class="relative h-5 w-9 rounded-full transition-colors duration-200" :class="form.supports_vision ? 'bg-emerald-500' : 'bg-[#d1d5db]'">
                        <div class="absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200" :class="form.supports_vision ? 'translate-x-[18px] left-0.5' : 'left-0.5'" />
                      </div>
                      <input v-model="form.supports_vision" type="checkbox" class="sr-only" />
                    </label>
                  </div>
                  <div ref="modelDropdownEl" class="relative">
                    <input v-model="form.model_name" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="gpt-4o" @keydown="handleModelDropdownKeydown" @focus="() => { if (availableModels.length > 0) showModelDropdown = true }" />
                    <div
                      v-if="showModelDropdown && availableModels.length > 0"
                      class="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded-xl border border-[#e5e7eb] bg-white py-1 shadow-lg"
                    >
                      <button
                        v-for="(name, i) in availableModels"
                        :key="name"
                        type="button"
                        :class="[
                          'flex w-full items-center px-3 py-2 text-left text-sm transition-colors',
                          i === modelDropdownIndex ? 'bg-[#f3f4f6] text-[#1f2937]' : 'text-[#374151] hover:bg-[#f9fafb]',
                        ]"
                        @click="selectModel(name)"
                        @mouseenter="modelDropdownIndex = i"
                      >
                        {{ name }}
                      </button>
                    </div>
                  </div>
                </label>
                <label class="block">
                  <span class="mb-1 block text-sm font-medium text-[#374151]">自定义指令</span>
                  <textarea v-model="form.user_instruction" class="w-full rounded-xl bg-[#f3f4f6] px-3 py-2 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" rows="3" placeholder="给 AI 的额外指令，例如：请用中文回答、回答要简洁..." />
                </label>
                <!-- 测试连接：放在高级参数之前，让用户先验证连通性再展开细节 -->
                <div class="flex items-center gap-2">
                  <button class="flex items-center gap-1.5 rounded-full bg-[#f3f4f6] px-4 py-2 text-sm text-[#374151] transition-colors hover:bg-[#e5e7eb]" type="button" :disabled="testing" @click="testConnection">
                    <span v-if="testing" class="h-3.5 w-3.5 border-2 border-[#9ca3af]/30 border-t-[#6b7280] rounded-full animate-spin" />
                    <svg v-else class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                    {{ testing ? '测试中...' : '测试连接' }}
                  </button>
                </div>
                <div v-if="testResult" class="rounded-xl px-3 py-2 text-xs" :class="testResult.success ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'">
                  {{ testResult.success ? '连接成功' : '连接失败' }}：{{ testResult.message }}
                </div>
                <div>
                  <button type="button" class="flex items-center gap-1 text-xs font-medium text-[#6b7280] hover:text-[#1f2937]" @click="showAdvanced = !showAdvanced">
                    <svg class="h-3 w-3 transition-transform" :class="showAdvanced ? 'rotate-90' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg>
                    高级参数
                  </button>
                  <div v-if="showAdvanced" class="mt-3 space-y-3">
                    <label class="block">
                      <div class="mb-1 flex items-center justify-between">
                        <span class="text-sm font-medium text-[#374151]">Temperature</span>
                        <button type="button" class="text-xs text-[#6b7280] hover:text-[#1f2937]" @click="form.temperature = null">重置</button>
                      </div>
                      <input v-model.number="form.temperature" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" type="number" min="0" max="2" step="0.1" placeholder="默认" />
                      <div class="mt-1 flex justify-between text-[10px] text-[#9ca3af]"><span>精确 (0)</span><span>创意 (2)</span></div>
                    </label>
                    <label class="block">
                      <div class="mb-1 flex items-center justify-between">
                        <span class="text-sm font-medium text-[#374151]">Max Tokens</span>
                        <button type="button" class="text-xs text-[#6b7280] hover:text-[#1f2937]" @click="form.max_tokens = null">重置</button>
                      </div>
                      <input v-model.number="form.max_tokens" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" type="number" min="1" max="128000" placeholder="留空使用默认值" />
                    </label>
                  </div>
                </div>
              </div>
            </template>
          </div>
          <!-- 浮动保存按钮：锚定在外层 relative 容器，不受内层 overflow 裁剪 -->
          <Transition name="fade">
            <button
              v-if="isModelFormDirty"
              class="absolute bottom-6 right-8 z-30 flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold shadow-xl active:scale-95 transition-all duration-200 disabled:cursor-not-allowed"
              :class="canSave ? 'bg-slate-900 text-white hover:bg-slate-800' : 'bg-slate-200 text-slate-400 shadow-none'"
              type="button"
              :disabled="!canSave || saving"
              :title="!testPassed ? '需要先测试连接成功后才能保存' : ''"
              @click="save"
            >
              <span v-if="saving" class="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
              <span>{{ saving ? '保存中...' : '保存修改' }}</span>
            </button>
          </Transition>
        </div>
      </div>

      <!-- 账号设置 Tab -->
      <div v-if="activeTab === 'account'" class="flex-1 overflow-y-auto p-5">
        <div v-if="accountLoading" class="py-8 text-center text-sm text-[#9ca3af]">加载中...</div>
        <template v-else-if="accountInfo">
          <div class="space-y-4">
            <div class="rounded-xl bg-[#f9fafb] p-4">
              <h3 class="mb-2 text-sm font-medium text-[#374151]">基本信息</h3>
              <div class="space-y-2">
                <div class="flex items-center gap-3"><span class="w-16 text-xs text-[#6b7280]">邮箱</span><span class="text-sm text-[#374151]">{{ accountInfo.email }}</span></div>
                <div class="flex items-center gap-3"><span class="w-16 text-xs text-[#6b7280]">用户 ID</span><span class="text-xs text-[#9ca3af] font-mono">{{ accountInfo.uuid.slice(0, 8) }}...</span></div>
              </div>
            </div>
            <div class="rounded-xl bg-[#f9fafb] p-4">
              <h3 class="mb-2 text-sm font-medium text-[#374151]">修改用户名</h3>
              <div class="flex items-end gap-3">
                <label class="flex-1"><input v-model="usernameForm.username" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="新用户名" maxlength="50" /></label>
                <Transition name="fade">
                  <button v-if="isUsernameDirty" class="flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-xl hover:bg-slate-800 active:scale-95 transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50" :disabled="!usernameForm.username.trim() || usernameSaving" @click="saveUsername"><span v-if="usernameSaving" class="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /><svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg><span>{{ usernameSaving ? '保存中...' : '保存修改' }}</span></button>
                </Transition>
              </div>
              <p v-if="usernameMsg" class="mt-2 text-xs" :class="usernameMsg.includes('已更新') ? 'text-emerald-600' : 'text-red-600'">{{ usernameMsg }}</p>
            </div>
            <div class="rounded-xl bg-[#f9fafb] p-4">
              <h3 class="mb-2 text-sm font-medium text-[#374151]">修改密码</h3>
              <div class="space-y-2">
                <input v-model="passwordForm.current_password" type="password" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="当前密码" />
                <input v-model="passwordForm.new_password" type="password" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="新密码" />
                 <input v-model="passwordForm.confirm_password" type="password" class="h-10 w-full rounded-xl bg-[#f3f4f6] px-3 text-sm outline-none transition focus:bg-[#e5e7eb] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="确认新密码" />
                <Transition name="fade">
                  <button v-if="isPasswordDirty" class="flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-xl hover:bg-slate-800 active:scale-95 transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50" :disabled="!passwordForm.current_password || !passwordForm.new_password || !passwordForm.confirm_password || passwordSaving" @click="savePassword"><span v-if="passwordSaving" class="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /><svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg><span>{{ passwordSaving ? '保存中...' : '修改密码' }}</span></button>
                </Transition>
              </div>
              <p v-if="passwordMsg" class="mt-2 text-xs" :class="passwordMsg.includes('已更新') ? 'text-emerald-600' : 'text-red-600'">{{ passwordMsg }}</p>
            </div>
          </div>
        </template>
      </div>

      <!-- 偏好设置 Tab -->
      <div v-if="activeTab === 'preferences'" class="relative flex-1 overflow-y-auto p-5">
        <div v-if="prefsLoading" class="py-8 text-center text-sm text-[#9ca3af]">加载中...</div>
        <template v-else>
          <div class="space-y-4">
            <div class="rounded-xl bg-[#f9fafb] p-4">
              <h3 class="mb-1 text-sm font-medium text-[#374151]">消息发送方式</h3>
              <p class="mb-2 text-xs text-[#9ca3af]">选择发送聊天消息的快捷键</p>
              <div class="space-y-1.5">
                <label class="flex cursor-pointer items-center gap-3 rounded-xl px-4 py-2.5 transition-all" :class="prefs.enter_mode === 'enter' ? 'bg-[#1f2937]/5 font-medium' : 'bg-white hover:bg-gray-100/50 shadow-sm'">
                  <input v-model="prefs.enter_mode" type="radio" value="enter" class="accent-[#1f2937]" />
                  <div><span class="text-sm font-medium text-[#374151]">Enter 发送</span><p class="text-xs text-[#9ca3af]">按 Enter 直接发送消息，Shift+Enter 换行</p></div>
                </label>
                <label class="flex cursor-pointer items-center gap-3 rounded-xl px-4 py-2.5 transition-all" :class="prefs.enter_mode === 'ctrl_enter' ? 'bg-[#1f2937]/5 font-medium' : 'bg-white hover:bg-gray-100/50 shadow-sm'">
                  <input v-model="prefs.enter_mode" type="radio" value="ctrl_enter" class="accent-[#1f2937]" />
                  <div><span class="text-sm font-medium text-[#374151]">Ctrl+Enter 发送</span><p class="text-xs text-[#9ca3af]">按 Ctrl+Enter 发送消息，Enter 换行</p></div>
                </label>
              </div>
              <p v-if="prefsMsg" class="mt-2 text-xs" :class="prefsMsg.includes('已保存') ? 'text-emerald-600' : 'text-red-600'">{{ prefsMsg }}</p>
            </div>
          </div>
          <!-- 浮动保存按钮：偏好设置 Tab 的全局保存，后期可扩展更多设置项 -->
          <Transition name="fade">
            <button
              v-if="isPrefsDirty"
              class="absolute bottom-6 right-8 z-30 flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-xl hover:bg-slate-800 active:scale-95 transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="prefsSaving"
              @click="savePreferences"
            >
              <span v-if="prefsSaving" class="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" /></svg>
              <span>{{ prefsSaving ? '保存中...' : '保存修改' }}</span>
            </button>
          </Transition>
        </template>
      </div>

      <!-- 删除确认弹窗 -->
      <div v-if="confirmDeleteId" class="absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-black/30">
        <div class="relative w-80 rounded-2xl bg-white p-5 shadow-xl">
          <button
            type="button"
            class="absolute top-4 right-4 text-[#9ca3af] hover:text-[#6b7280] transition-colors"
            :disabled="deleting"
            @click="cancelDelete"
          >
            <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <div class="mb-1 text-sm font-semibold text-[#1f2937]">删除配置</div>
          <div class="mb-4 text-sm text-[#6b7280]">确定删除「{{ confirmDeleteName }}」？此操作不可恢复。</div>
          <div class="flex justify-end">
            <button class="h-8 rounded-xl bg-[#b91c1c] hover:bg-[#991b1b] px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60" :disabled="deleting" @click="performDelete">{{ deleting ? '删除中...' : '删除' }}</button>
          </div>
        </div>
      </div>
    </div>
    <!-- 视觉模型 tooltip：Teleport 到 body 层，完全避开 overflow 裁剪 -->
    <Teleport to="body">
      <div
        v-if="showVisionTooltip"
        class="pointer-events-none fixed z-[999] w-56 rounded-xl bg-slate-800 px-3 py-2 text-xs leading-relaxed text-white shadow-lg"
        :style="{ top: visionTooltipPos.top + 'px', left: visionTooltipPos.left + 'px' }"
      >
        视觉模型用于解析图片内容。若主模型不支持多模态图片输入，系统会自动调用此配置的视觉模型来理解和描述图片，再将文本描述传递给主模型处理。
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
