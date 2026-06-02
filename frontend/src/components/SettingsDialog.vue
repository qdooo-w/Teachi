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
  getAccountInfo,
  updateUsername,
  changePassword,
  getPreferences,
  updatePreferences,
  getErrorMessage,
} from '../api'

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
const errorMsg = ref('')
const testResult = ref<TestConnectionResponse | null>(null)
const editingId = ref<string | null>(null)
const isCreating = computed(() => editingId.value === 'create')

const testPassed = ref(false)
const isInitializing = ref(false)

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
const canSave = computed(() => form.value.config_name.trim().length > 0 && testPassed.value)

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


function cancelEdit(): void { editingId.value = null; testResult.value = null; errorMsg.value = '' }

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

const accountInfo = ref<AccountInfo | null>(null)
const accountLoading = ref(false)
const usernameForm = ref({ username: '' })
const passwordForm = ref({ current_password: '', new_password: '', confirm_password: '' })
const usernameSaving = ref(false)
const passwordSaving = ref(false)
const usernameMsg = ref('')
const passwordMsg = ref('')

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

const prefs = ref<Preferences>({ enter_mode: 'enter', updated_at: null })
const prefsLoading = ref(false)
const prefsSaving = ref(false)
const prefsMsg = ref('')

async function loadPreferences(): Promise<void> {
  prefsLoading.value = true
  try { prefs.value = await getPreferences() }
  catch (e) { /* ignore */ }
  finally { prefsLoading.value = false }
}

async function savePreferences(): Promise<void> {
  prefsSaving.value = true; prefsMsg.value = ''
  try { prefs.value = await updatePreferences({ enter_mode: prefs.value.enter_mode }); prefsMsg.value = '偏好已保存' }
  catch (e) { prefsMsg.value = getErrorMessage(e) }
  finally { prefsSaving.value = false }
}

onMounted(() => { loadConfigs(); loadAccountInfo(); loadPreferences() })
</script>

﻿
<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
    <div class="relative flex h-[560px] w-[640px] flex-col rounded-xl bg-white shadow-2xl">
      <!-- Tab 栏 -->
      <div class="flex border-b border-[#e5e7eb] px-5 pt-3">
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
      </div>

      <!-- 模型配置 Tab -->
      <div v-if="activeTab === 'model'" class="flex flex-1 overflow-hidden">
        <div class="w-56 flex-shrink-0 border-r border-[#e5e7eb] overflow-y-auto p-3">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-xs font-medium text-[#6b7280]">配置列表</span>
            <button class="text-xs text-[#1f2937] hover:text-[#111827]" @click="startCreate">+ 新增</button>
          </div>
          <div v-if="loading" class="py-4 text-center text-xs text-[#9ca3af]">加载中...</div>
          <div v-else-if="configs.length === 0" class="py-4 text-center text-xs text-[#9ca3af]">暂无配置</div>
          <div v-for="config in configs" :key="config.config_id" class="group relative">
            <div class="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors cursor-pointer" :class="editingId === config.config_id ? 'bg-[#f3f4f6] text-[#1f2937]' : 'text-[#374151] hover:bg-[#f9fafb]'" @click="startEdit(config)">
              <span class="inline-block h-2 w-2 flex-shrink-0 rounded-full cursor-pointer" :class="config.is_active ? 'bg-emerald-500' : 'bg-[#d1d5db]'" :title="config.is_active ? '取消激活' : '设为激活'" @click.stop="handleActivate(config)" />
              <span class="truncate">{{ config.config_name }}</span>
            </div>
            <button v-if="editingId === config.config_id" class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-[#9ca3af] opacity-0 transition hover:text-red-500 group-hover:opacity-100" title="删除" @click.stop="requestDelete(config)">
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto p-5">
          <div v-if="errorMsg" class="mb-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{{ errorMsg }}</div>
          <template v-if="editingId === null">
            <div class="flex flex-col items-center justify-center py-12 text-center">
              <svg class="mb-3 h-10 w-10 text-[#d1d5db]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
              <p class="mb-1 text-sm font-medium text-[#374151]">模型配置</p>
              <p class="text-xs text-[#9ca3af]">选择左侧配置编辑，或新增一个</p>
            </div>
          </template>
          <template v-else>
            <div class="mb-3 flex items-center justify-between">
              <button type="button" class="flex items-center gap-1 text-xs text-[#6b7280] hover:text-[#1f2937]" @click="cancelEdit">
                <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" /></svg>
                返回列表
              </button>
            </div>
            <div class="space-y-4">
              <label class="block">
                <span class="mb-1 block text-sm font-medium text-[#374151]">配置名称 <span class="text-red-500">*</span></span>
                <input v-model="form.config_name" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="例如：GPT-4o" />
              </label>
              <label class="block">
                <div class="mb-1 flex items-center justify-between">
                  <span class="text-sm font-medium text-[#374151]">API Key</span>
                  <button type="button" class="text-xs text-[#6b7280] hover:text-[#1f2937]" @click="showApiKey = !showApiKey">{{ showApiKey ? '隐藏' : '显示' }}</button>
                </div>
                <input v-model="form.api_key" :type="showApiKey ? 'text' : 'password'" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="sk-..." />
              </label>
              <label class="block">
                <span class="mb-1 block text-sm font-medium text-[#374151]">Base URL</span>
                <input v-model="form.base_url" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="https://api.openai.com/v1" />
              </label>
              <label class="block">
                <span class="mb-1 block text-sm font-medium text-[#374151]">模型名称</span>
                <input v-model="form.model_name" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="gpt-4o" />
              </label>
              <label class="block">
                <span class="mb-1 block text-sm font-medium text-[#374151]">自定义指令</span>
                <textarea v-model="form.user_instruction" class="w-full rounded-md border border-[#d1d5db] bg-white px-3 py-2 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" rows="3" placeholder="给 AI 的额外指令，例如：请用中文回答、回答要简洁..." />
              </label>
              <div>
                <button type="button" class="flex items-center gap-1 text-xs font-medium text-[#6b7280] hover:text-[#1f2937]" @click="showAdvanced = !showAdvanced">
                  <svg class="h-3 w-3 transition-transform" :class="showAdvanced ? 'rotate-90' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg>
                  高级参数
                </button>
                <div v-if="showAdvanced" class="mt-3 space-y-4">
                  <label class="block">
                    <div class="mb-1 flex items-center justify-between">
                      <span class="text-sm font-medium text-[#374151]">Temperature</span>
                      <button type="button" class="text-xs text-[#6b7280] hover:text-[#1f2937]" @click="form.temperature = null">重置</button>
                    </div>
                    <input v-model.number="form.temperature" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" type="number" min="0" max="2" step="0.1" placeholder="默认" />
                    <div class="mt-1 flex justify-between text-[10px] text-[#9ca3af]"><span>精确 (0)</span><span>创意 (2)</span></div>
                  </label>
                  <label class="block">
                    <div class="mb-1 flex items-center justify-between">
                      <span class="text-sm font-medium text-[#374151]">Max Tokens</span>
                      <button type="button" class="text-xs text-[#6b7280] hover:text-[#1f2937]" @click="form.max_tokens = null">重置</button>
                    </div>
                    <input v-model.number="form.max_tokens" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" type="number" min="1" max="128000" placeholder="留空使用默认值" />
                  </label>

                  <!-- Supports Vision -->
                  <label class="flex items-center gap-2 cursor-pointer py-1">
                    <input
                      v-model="form.supports_vision"
                      type="checkbox"
                      class="h-4 w-4 rounded border-[#d1d5db] text-[#1f2937] focus:ring-[#1f2937]/20"
                    />
                    <span class="text-sm font-medium text-[#374151]">此模型支持视觉（图片输入）</span>
                  </label>
                </div>
              </div>
              <div v-if="testResult" class="rounded-md px-3 py-2 text-xs" :class="testResult.success ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'">
                {{ testResult.success ? '连接成功' : '连接失败' }}：{{ testResult.message }}
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 账号设置 Tab -->
      <div v-if="activeTab === 'account'" class="flex-1 overflow-y-auto p-5">
        <div v-if="accountLoading" class="py-8 text-center text-sm text-[#9ca3af]">加载中...</div>
        <template v-else-if="accountInfo">
          <div class="space-y-6">
            <div class="rounded-lg border border-[#e5e7eb] p-4">
              <h3 class="mb-3 text-sm font-medium text-[#374151]">基本信息</h3>
              <div class="space-y-3">
                <div class="flex items-center gap-3"><span class="w-16 text-xs text-[#6b7280]">邮箱</span><span class="text-sm text-[#374151]">{{ accountInfo.email }}</span></div>
                <div class="flex items-center gap-3"><span class="w-16 text-xs text-[#6b7280]">用户 ID</span><span class="text-xs text-[#9ca3af] font-mono">{{ accountInfo.uuid.slice(0, 8) }}...</span></div>
              </div>
            </div>
            <div class="rounded-lg border border-[#e5e7eb] p-4">
              <h3 class="mb-3 text-sm font-medium text-[#374151]">修改用户名</h3>
              <div class="flex items-end gap-3">
                <label class="flex-1"><input v-model="usernameForm.username" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="新用户名" maxlength="50" /></label>
                <button class="h-10 rounded-md bg-[#1f2937] px-4 text-sm font-medium text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]" :disabled="!usernameForm.username.trim() || usernameSaving" @click="saveUsername">{{ usernameSaving ? '保存中...' : '保存' }}</button>
              </div>
              <p v-if="usernameMsg" class="mt-2 text-xs" :class="usernameMsg.includes('已更新') ? 'text-emerald-600' : 'text-red-600'">{{ usernameMsg }}</p>
            </div>
            <div class="rounded-lg border border-[#e5e7eb] p-4">
              <h3 class="mb-3 text-sm font-medium text-[#374151]">修改密码</h3>
              <div class="space-y-3">
                <input v-model="passwordForm.current_password" type="password" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="当前密码" />
                <input v-model="passwordForm.new_password" type="password" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="新密码" />
                <input v-model="passwordForm.confirm_password" type="password" class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20" placeholder="确认新密码" />
                <button class="h-10 rounded-md bg-[#1f2937] px-4 text-sm font-medium text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]" :disabled="!passwordForm.current_password || !passwordForm.new_password || !passwordForm.confirm_password || passwordSaving" @click="savePassword">{{ passwordSaving ? '保存中...' : '修改密码' }}</button>
              </div>
              <p v-if="passwordMsg" class="mt-2 text-xs" :class="passwordMsg.includes('已更新') ? 'text-emerald-600' : 'text-red-600'">{{ passwordMsg }}</p>
            </div>
          </div>
        </template>
      </div>

      <!-- 偏好设置 Tab -->
      <div v-if="activeTab === 'preferences'" class="flex-1 overflow-y-auto p-5">
        <div v-if="prefsLoading" class="py-8 text-center text-sm text-[#9ca3af]">加载中...</div>
        <template v-else>
          <div class="space-y-6">
            <div class="rounded-lg border border-[#e5e7eb] p-4">
              <h3 class="mb-1 text-sm font-medium text-[#374151]">消息发送方式</h3>
              <p class="mb-3 text-xs text-[#9ca3af]">选择发送聊天消息的快捷键</p>
              <div class="space-y-2">
                <label class="flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 transition-colors" :class="prefs.enter_mode === 'enter' ? 'border-[#1f2937] bg-[#f9fafb]' : 'border-[#e5e7eb] hover:bg-[#f9fafb]'">
                  <input v-model="prefs.enter_mode" type="radio" value="enter" class="accent-[#1f2937]" />
                  <div><span class="text-sm font-medium text-[#374151]">Enter 发送</span><p class="text-xs text-[#9ca3af]">按 Enter 直接发送消息，Shift+Enter 换行</p></div>
                </label>
                <label class="flex cursor-pointer items-center gap-3 rounded-lg border px-4 py-3 transition-colors" :class="prefs.enter_mode === 'ctrl_enter' ? 'border-[#1f2937] bg-[#f9fafb]' : 'border-[#e5e7eb] hover:bg-[#f9fafb]'">
                  <input v-model="prefs.enter_mode" type="radio" value="ctrl_enter" class="accent-[#1f2937]" />
                  <div><span class="text-sm font-medium text-[#374151]">Ctrl+Enter 发送</span><p class="text-xs text-[#9ca3af]">按 Ctrl+Enter 发送消息，Enter 换行</p></div>
                </label>
              </div>
              <div class="mt-4 flex items-center gap-3">
                <button class="h-9 rounded-md bg-[#1f2937] px-4 text-sm font-medium text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]" :disabled="prefsSaving" @click="savePreferences">{{ prefsSaving ? '保存中...' : '保存' }}</button>
                <p v-if="prefsMsg" class="text-xs" :class="prefsMsg.includes('已保存') ? 'text-emerald-600' : 'text-red-600'">{{ prefsMsg }}</p>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 底部操作栏 -->
      <div class="flex h-14 flex-shrink-0 items-center justify-between border-t border-[#e5e7eb] px-5">
        <div class="text-xs text-[#9ca3af]">
          <template v-if="activeTab === 'model'">
            <template v-if="editingId === null">{{ configs.length }} 个配置</template>
            <template v-else>{{ isCreating ? '新建配置' : '编辑配置' }}</template>
          </template>
        </div>
        <div class="flex items-center gap-2">
          <template v-if="activeTab === 'model' && editingId !== null">
            <button class="flex h-9 items-center gap-1.5 rounded-md border border-[#d1d5db] px-4 text-sm text-[#374151] transition-colors hover:bg-[#f3f4f6]" type="button" :disabled="testing" @click="testConnection">
              <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
              {{ testing ? '测试中...' : '测试连接' }}
            </button>
            <button class="h-9 rounded-md bg-[#1f2937] px-5 text-sm font-medium text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]" type="button" :disabled="!canSave || saving" :title="!testPassed ? '需要先测试连接成功后才能保存' : ''" @click="save">{{ saving ? '保存中...' : '保存' }}</button>
          </template>
          <button class="h-9 rounded-md border border-[#d1d5db] px-4 text-sm text-[#374151] transition-colors hover:bg-[#f3f4f6]" type="button" @click="emit('close')">关闭</button>
        </div>
      </div>

      <!-- 删除确认弹窗 -->
      <div v-if="confirmDeleteId" class="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-black/30">
        <div class="w-80 rounded-lg bg-white p-5 shadow-xl">
          <div class="mb-1 text-sm font-semibold text-[#1f2937]">删除配置</div>
          <div class="mb-4 text-sm text-[#6b7280]">确定删除「{{ confirmDeleteName }}」？此操作不可恢复。</div>
          <div class="flex justify-end gap-2">
            <button class="h-8 rounded-md border border-[#d1d5db] px-3 text-sm text-[#374151] hover:bg-[#f3f4f6]" :disabled="deleting" @click="cancelDelete">取消</button>
            <button class="h-8 rounded-md bg-[#ef4444] px-3 text-sm font-medium text-white hover:bg-[#dc2626] disabled:cursor-not-allowed disabled:bg-[#f87171]" :disabled="deleting" @click="performDelete">{{ deleting ? '删除中...' : '删除' }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
