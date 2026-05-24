
<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  type ModelConfigItem,
  type CreateModelConfigRequest,
  type UpdateModelConfigRequest,
  type TestConnectionResponse,
  listModelConfigs,
  createModelConfig,
  updateModelConfig,
  activateModelConfig,
  deactivateAllModelConfigs,
  deleteModelConfig,
  testConnectionWithParams,
  testConnectionWithConfig,
  getErrorMessage,
} from '../api'

const emit = defineEmits<{
  close: []
}>()

// ── 状态 ──────────────────────────────────────────────────────────────────────
const configs = ref<ModelConfigItem[]>([])
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const testing = ref(false)
const errorMsg = ref('')
const testResult = ref<TestConnectionResponse | null>(null)

// 编辑模式：null = 列表, 'create' = 新建, config_id = 编辑
const editingId = ref<string | null>(null)
const isCreating = computed(() => editingId.value === 'create')
const isEditing = computed(() => editingId.value !== null && editingId.value !== 'create')

// ── 表单 ──────────────────────────────────────────────────────────────────────
const form = ref({
  config_name: '',
  api_key: '',
  base_url: '',
  model_name: '',
  temperature: null as number | null,
  max_tokens: null as number | null,
})
const showAdvanced = ref(false)
const showApiKey = ref(false)

// 记录编辑时原始 api_key 是否为脱敏值（以 * 开头）
const apiKeyIsMasked = ref(false)

// ── 删除确认 ──────────────────────────────────────────────────────────────────
const confirmDeleteId = ref<string | null>(null)
const confirmDeleteName = ref('')

// ── 计算属性 ──────────────────────────────────────────────────────────────────
const activeConfig = computed(() => configs.value.find((c) => c.is_active) ?? null)

const canSave = computed(() => {
  return form.value.config_name.trim().length > 0
})

// ── 数据加载 ──────────────────────────────────────────────────────────────────
async function loadConfigs(): Promise<void> {
  loading.value = true
  errorMsg.value = ''
  try {
    configs.value = await listModelConfigs()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    loading.value = false
  }
}

// ── 编辑操作 ──────────────────────────────────────────────────────────────────
function startCreate(): void {
  editingId.value = 'create'
  form.value = {
    config_name: '',
    api_key: '',
    base_url: '',
    model_name: '',
    temperature: null,
    max_tokens: null,
  }
  showAdvanced.value = false
  showApiKey.value = false
  apiKeyIsMasked.value = false
  testResult.value = null
  errorMsg.value = ''
}

function startEdit(config: ModelConfigItem): void {
  editingId.value = config.config_id
  form.value = {
    config_name: config.config_name,
    api_key: config.api_key,
    base_url: config.base_url,
    model_name: config.model_name,
    temperature: config.temperature,
    max_tokens: config.max_tokens,
  }
  showAdvanced.value = config.temperature !== null || config.max_tokens !== null
  showApiKey.value = false
  apiKeyIsMasked.value = config.api_key.startsWith('*')
  testResult.value = null
  errorMsg.value = ''
}

function cancelEdit(): void {
  editingId.value = null
  testResult.value = null
  errorMsg.value = ''
}

// ── 保存 ──────────────────────────────────────────────────────────────────────
async function save(): Promise<void> {
  if (!canSave.value) return
  saving.value = true
  errorMsg.value = ''
  try {
    if (isCreating.value) {
      const payload: CreateModelConfigRequest = {
        config_name: form.value.config_name.trim(),
        api_key: form.value.api_key,
        base_url: form.value.base_url,
        model_name: form.value.model_name,
        temperature: form.value.temperature,
        max_tokens: form.value.max_tokens,
        is_active: false,
      }
      await createModelConfig(payload)
    } else if (editingId.value) {
      const payload: UpdateModelConfigRequest = {
        config_name: form.value.config_name.trim(),
        base_url: form.value.base_url,
        model_name: form.value.model_name,
        temperature: form.value.temperature,
        max_tokens: form.value.max_tokens,
      }
      // 仅当用户修改了脱敏的 api_key 时才发送
      if (!apiKeyIsMasked.value || !form.value.api_key.startsWith('*')) {
        payload.api_key = form.value.api_key
      }
      await updateModelConfig(editingId.value, payload)
    }
    editingId.value = null
    await loadConfigs()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    saving.value = false
  }
}

// ── 激活/取消激活 ─────────────────────────────────────────────────────────────
async function toggleActive(config: ModelConfigItem): Promise<void> {
  errorMsg.value = ''
  try {
    if (config.is_active) {
      await deactivateAllModelConfigs()
    } else {
      await activateModelConfig(config.config_id)
    }
    await loadConfigs()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  }
}

// ── 删除 ──────────────────────────────────────────────────────────────────────
function askDelete(config: ModelConfigItem): void {
  confirmDeleteId.value = config.config_id
  confirmDeleteName.value = config.config_name
}

function cancelDelete(): void {
  confirmDeleteId.value = null
  confirmDeleteName.value = ''
}

async function performDelete(): Promise<void> {
  if (!confirmDeleteId.value) return
  deleting.value = true
  errorMsg.value = ''
  try {
    await deleteModelConfig(confirmDeleteId.value)
    if (editingId.value === confirmDeleteId.value) {
      editingId.value = null
    }
    confirmDeleteId.value = null
    confirmDeleteName.value = ''
    await loadConfigs()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    deleting.value = false
  }
}

// ── 测试连接 ──────────────────────────────────────────────────────────────────
async function testConnection(): Promise<void> {
  testing.value = true
  testResult.value = null
  errorMsg.value = ''
  try {
    if (isEditing.value && editingId.value && form.value.api_key.startsWith('*')) {
      // 使用已保存配置测试
      testResult.value = await testConnectionWithConfig(editingId.value)
    } else {
      // 使用表单参数测试
      testResult.value = await testConnectionWithParams({
        api_key: form.value.api_key,
        base_url: form.value.base_url,
        model_name: form.value.model_name,
      })
    }
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    testing.value = false
  }
}

async function testExistingConnection(config: ModelConfigItem): Promise<void> {
  testing.value = true
  testResult.value = null
  errorMsg.value = ''
  try {
    testResult.value = await testConnectionWithConfig(config.config_id)
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    testing.value = false
  }
}

// ── 关闭 ──────────────────────────────────────────────────────────────────────
function handleClose(): void {
  emit('close')
}

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') handleClose()
}

// ── 生命周期 ──────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadConfigs()
  document.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40" @click.self="handleClose">
    <div class="flex h-[580px] w-[640px] max-w-[96vw] flex-col rounded-xl bg-white shadow-xl">
      <!-- 头部 -->
      <div class="flex h-14 flex-shrink-0 items-center justify-between border-b border-[#e5e7eb] px-5">
        <span class="font-semibold text-[#1f2937]">AI 模型配置</span>
        <button
          class="flex h-8 w-8 items-center justify-center rounded-md text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#1f2937]"
          type="button"
          @click="handleClose"
        >
          <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- 错误提示 -->
      <div
        v-if="errorMsg"
        class="mx-5 mt-3 flex items-center justify-between rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]"
        role="alert"
      >
        <span class="truncate">{{ errorMsg }}</span>
        <button class="ml-3 flex-shrink-0 hover:text-[#7c2d12]" type="button" @click="errorMsg = ''">
          <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- 测试连接结果 -->
      <div
        v-if="testResult"
        class="mx-5 mt-3 flex items-center justify-between rounded-md border px-3 py-2 text-sm"
        :class="[
          testResult.success
            ? 'border-[#a7f3d0] bg-[#ecfdf5] text-[#065f46]'
            : 'border-[#efb3a7] bg-[#fff7ed] text-[#9a3412]',
        ]"
        role="status"
      >
        <span class="truncate">
          {{ testResult.success ? `✓ 连接成功${testResult.model ? ` (${testResult.model})` : ''}` : `✗ ${testResult.message}` }}
        </span>
        <button class="ml-3 flex-shrink-0 opacity-70 hover:opacity-100" type="button" @click="testResult = null">
          <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- 主体内容 -->
      <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <!-- 列表视图 -->
        <template v-if="editingId === null">
          <!-- 当前激活提示 -->
          <div v-if="activeConfig" class="mb-4 flex items-center gap-2 rounded-lg border border-[#a7f3d0] bg-[#ecfdf5] px-3 py-2.5 text-sm">
            <span class="inline-block h-2 w-2 flex-shrink-0 rounded-full bg-[#10b981]"></span>
            <span class="text-[#065f46]">当前激活：<strong>{{ activeConfig.config_name }}</strong></span>
            <span class="text-[#6b7280]">·</span>
            <span class="text-[#6b7280]">{{ activeConfig.model_name || '未设置模型' }}</span>
          </div>
          <div v-else class="mb-4 flex items-center gap-2 rounded-lg border border-[#fcd34d] bg-[#fefce8] px-3 py-2.5 text-sm text-[#92400e]">
            <span class="inline-block h-2 w-2 flex-shrink-0 rounded-full bg-[#f59e0b]"></span>
            尚未激活任何配置，将使用环境变量默认值
          </div>

          <!-- 配置列表 -->
          <div v-if="loading" class="py-8 text-center text-sm text-[#9ca3af]">加载中...</div>
          <div v-else-if="configs.length === 0" class="py-8 text-center text-sm text-[#9ca3af]">
            暂无配置，点击下方按钮创建
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="config in configs"
              :key="config.config_id"
              class="group rounded-lg border px-4 py-3 transition-colors"
              :class="[
                config.is_active
                  ? 'border-[#1f6f5b]/30 bg-[#e6f4ee]'
                  : 'border-[#e5e7eb] bg-white hover:border-[#d1d5db]',
              ]"
            >
              <div class="flex items-center justify-between">
                <div class="flex min-w-0 items-center gap-3">
                  <!-- 激活开关 -->
                  <button
                    type="button"
                    class="flex h-5 w-9 flex-shrink-0 items-center rounded-full p-0.5 transition-colors"
                    :class="config.is_active ? 'bg-[#1f6f5b]' : 'bg-[#d1d5db]'"
                    :title="config.is_active ? '点击取消激活' : '点击激活'"
                    @click="toggleActive(config)"
                  >
                    <span
                      class="block h-4 w-4 rounded-full bg-white shadow-sm transition-transform"
                      :class="config.is_active ? 'translate-x-4' : 'translate-x-0'"
                    ></span>
                  </button>
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="truncate text-sm font-medium text-[#1f2937]">{{ config.config_name }}</span>
                      <span v-if="config.is_active" class="rounded-full bg-[#1f6f5b] px-2 py-0.5 text-[10px] font-medium text-white">激活</span>
                    </div>
                    <div class="mt-0.5 truncate text-xs text-[#6b7280]">
                      {{ config.model_name || '未设置' }} · {{ config.base_url || '默认 URL' }} · {{ config.api_key ? config.api_key : '无 Key' }}
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    class="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#1f2937]"
                    type="button"
                    title="测试连接"
                    :disabled="testing"
                    @click="testExistingConnection(config)"
                  >
                    <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    测试
                  </button>
                  <button
                    class="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#1f2937]"
                    type="button"
                    @click="startEdit(config)"
                  >
                    <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                    编辑
                  </button>
                  <button
                    class="flex h-7 items-center gap-1 rounded-md px-2 text-xs text-[#ef4444] hover:bg-[#fef2f2]"
                    type="button"
                    @click="askDelete(config)"
                  >
                    <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                    删除
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 新建按钮 -->
          <button
            class="mt-4 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-[#d1d5db] py-2.5 text-sm text-[#6b7280] transition-colors hover:border-[#1f6f5b] hover:bg-[#e6f4ee] hover:text-[#1f6f5b]"
            type="button"
            @click="startCreate"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
            </svg>
            新建配置
          </button>
        </template>

        <!-- 编辑/新建视图 -->
        <template v-else>
          <button
            class="mb-4 flex items-center gap-1 text-sm text-[#6b7280] hover:text-[#1f2937]"
            type="button"
            @click="cancelEdit"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
            </svg>
            返回列表
          </button>

          <div class="space-y-4">
            <!-- 配置名称 -->
            <label class="block">
              <span class="mb-1 block text-sm font-medium text-[#374151]">配置名称 <span class="text-[#ef4444]">*</span></span>
              <input
                v-model="form.config_name"
                class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                type="text"
                placeholder="如：GPT-4o、DeepSeek"
                maxlength="100"
                autocomplete="off"
              />
            </label>

            <!-- API Key -->
            <label class="block">
              <span class="mb-1 block text-sm font-medium text-[#374151]">API Key</span>
              <div class="relative">
                <input
                  v-model="form.api_key"
                  class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 pr-10 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                  type="text"
                  :style="!showApiKey ? { WebkitTextSecurity: 'disc' } : {}"
                  placeholder="sk-..."
                  maxlength="500"
                  autocomplete="off"
                  data-1p-ignore
                  data-lpignore="true"
                />
                <button
                  class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#9ca3af] hover:text-[#6b7280]"
                  type="button"
                  @click="showApiKey = !showApiKey"
                >
                  <svg v-if="!showApiKey" class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                  <svg v-else class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                  </svg>
                </button>
              </div>
              <p v-if="isEditing && apiKeyIsMasked" class="mt-1 text-xs text-[#9ca3af]">留空则保留原值，修改后请输入完整 Key</p>
            </label>

            <!-- Base URL -->
            <label class="block">
              <span class="mb-1 block text-sm font-medium text-[#374151]">Base URL</span>
              <input
                v-model="form.base_url"
                class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                type="text"
                placeholder="https://api.openai.com/v1"
                maxlength="500"
                autocomplete="off"
              />
            </label>

            <!-- 模型名称 -->
            <label class="block">
              <span class="mb-1 block text-sm font-medium text-[#374151]">模型名称</span>
              <input
                v-model="form.model_name"
                class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                type="text"
                placeholder="如：gpt-4o、deepseek-chat"
                maxlength="200"
                autocomplete="off"
              />
            </label>

            <!-- 高级选项折叠 -->
            <div class="rounded-lg border border-[#e5e7eb]">
              <button
                type="button"
                class="flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium text-[#374151] hover:bg-[#f9fafb]"
                @click="showAdvanced = !showAdvanced"
              >
                <span>高级选项</span>
                <svg
                  class="h-4 w-4 text-[#6b7280] transition-transform"
                  :class="{ 'rotate-180': showAdvanced }"
                  aria-hidden="true"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <div v-if="showAdvanced" class="border-t border-[#e5e7eb] px-4 py-3 space-y-4">
                <!-- Temperature -->
                <label class="block">
                  <div class="mb-1 flex items-center justify-between">
                    <span class="text-sm font-medium text-[#374151]">Temperature</span>
                    <span class="text-xs text-[#6b7280]">{{ form.temperature !== null ? form.temperature.toFixed(1) : '默认' }}</span>
                  </div>
                  <div class="flex items-center gap-3">
                    <input
                      v-model.number="form.temperature"
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      class="h-2 flex-1 cursor-pointer appearance-none rounded-lg bg-[#e5e7eb] accent-[#1f6f5b]"
                    />
                    <button
                      type="button"
                      class="text-xs text-[#6b7280] hover:text-[#1f2937]"
                      title="重置为默认"
                      @click="form.temperature = null"
                    >
                      重置
                    </button>
                  </div>
                  <div class="mt-1 flex justify-between text-[10px] text-[#9ca3af]">
                    <span>精确 (0)</span>
                    <span>创意 (2)</span>
                  </div>
                </label>

                <!-- Max Tokens -->
                <label class="block">
                  <div class="mb-1 flex items-center justify-between">
                    <span class="text-sm font-medium text-[#374151]">Max Tokens</span>
                    <span class="text-xs text-[#6b7280]">{{ form.max_tokens !== null ? form.max_tokens : '默认' }}</span>
                  </div>
                  <div class="flex items-center gap-3">
                    <input
                      v-model.number="form.max_tokens"
                      class="h-10 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                      type="number"
                      min="1"
                      max="128000"
                      placeholder="留空使用默认值"
                    />
                    <button
                      type="button"
                      class="text-xs text-[#6b7280] hover:text-[#1f2937]"
                      title="重置为默认"
                      @click="form.max_tokens = null"
                    >
                      重置
                    </button>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 底部操作栏 -->
      <div class="flex h-14 flex-shrink-0 items-center justify-between border-t border-[#e5e7eb] px-5">
        <div class="text-xs text-[#9ca3af]">
          <template v-if="editingId === null">{{ configs.length }} 个配置</template>
          <template v-else>{{ isCreating ? '新建配置' : '编辑配置' }}</template>
        </div>
        <div class="flex items-center gap-2">
          <template v-if="editingId !== null">
            <button
              class="flex h-9 items-center gap-1.5 rounded-md border border-[#d1d5db] px-4 text-sm text-[#374151] transition-colors hover:bg-[#f3f4f6]"
              type="button"
              :disabled="testing"
              @click="testConnection"
            >
              <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              {{ testing ? '测试中...' : '测试连接' }}
            </button>
            <button
              class="h-9 rounded-md bg-[#1f2937] px-5 text-sm font-medium text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]"
              type="button"
              :disabled="!canSave || saving"
              @click="save"
            >
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </template>
          <button
            class="h-9 rounded-md border border-[#d1d5db] px-4 text-sm text-[#374151] transition-colors hover:bg-[#f3f4f6]"
            type="button"
            @click="handleClose"
          >
            关闭
          </button>
        </div>
      </div>

      <!-- 删除确认弹窗 -->
      <div
        v-if="confirmDeleteId"
        class="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-black/30"
      >
        <div class="w-80 rounded-lg bg-white p-5 shadow-xl">
          <div class="mb-1 text-sm font-semibold text-[#1f2937]">删除配置</div>
          <div class="mb-4 text-sm text-[#6b7280]">
            确定删除「{{ confirmDeleteName }}」？此操作不可恢复。
          </div>
          <div class="flex justify-end gap-2">
            <button
              class="h-8 rounded-md border border-[#d1d5db] px-3 text-sm text-[#374151] hover:bg-[#f3f4f6]"
              type="button"
              :disabled="deleting"
              @click="cancelDelete"
            >
              取消
            </button>
            <button
              class="h-8 rounded-md bg-[#ef4444] px-3 text-sm font-medium text-white hover:bg-[#dc2626] disabled:cursor-not-allowed disabled:bg-[#f87171]"
              type="button"
              :disabled="deleting"
              @click="performDelete"
            >
              {{ deleting ? '删除中...' : '删除' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
