<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  type FileSpace,
  type SkillMeta,
  type SkillFields,
  listSkills,
  readSkill,
  writeSkill,
  deleteSkill,
  validateSkillName,
  parseSkillFile,
  buildSkillFile,
} from '../skills'
import { getErrorMessage } from '../api'
import { publishCommunitySkill } from '../api'

const props = defineProps<{
  space: FileSpace
  title: string
  initialSkill?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const skills = ref<SkillMeta[]>([])
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const publishing = ref(false)
const errorMsg = ref('')
const publishMsg = ref('')

// 编辑状态：结构化字段
const selectedName = ref<string | null>(null)
const isNew = ref(false)
const form = ref<SkillFields>({
  name: '',
  description: '',
  license: '',
  compatibility: '',
  body: '',
})
const showAdvanced = ref(false)
const dirty = ref(false)
// 原始文件无法被结构化解析时，退化为原始 textarea 编辑模式
const rawMode = ref(false)
const rawContent = ref('')
const parseWarning = ref('')

const nameError = computed(() => {
  if (!isNew.value) return null
  return validateSkillName(form.value.name)
})

// 官方 Skills 规范硬限制
const DESCRIPTION_MAX = 1024
const COMPATIBILITY_MAX = 500

const descriptionError = computed(() => {
  const d = form.value.description
  if (!d.trim()) return '描述不能为空（会作为技能对模型的说明）'
  if (d.length > DESCRIPTION_MAX) return `描述不能超过 ${DESCRIPTION_MAX} 字符（当前 ${d.length}）`
  return null
})

const compatibilityError = computed(() => {
  const c = form.value.compatibility ?? ''
  if (c.length > COMPATIBILITY_MAX) return `compatibility 不能超过 ${COMPATIBILITY_MAX} 字符（当前 ${c.length}）`
  return null
})

// 正文仅作参考计数，不限制大小
const bodyCharCount = computed(() => form.value.body.length)
const bodyLineCount = computed(() => form.value.body.split('\n').length)

const canSave = computed(() => {
  if (rawMode.value) return !saving.value && rawContent.value.trim().length > 0
  if (saving.value) return false
  if (isNew.value && nameError.value) return false
  if (descriptionError.value) return false
  if (compatibilityError.value) return false
  return true
})

async function loadSkills() {
  loading.value = true
  errorMsg.value = ''
  try {
    skills.value = await listSkills(props.space)
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.value = { name: '', description: '', license: '', compatibility: '', body: '' }
  showAdvanced.value = false
  rawMode.value = false
  rawContent.value = ''
  parseWarning.value = ''
  dirty.value = false
}

async function selectSkill(name: string) {
  if (dirty.value && !confirm('有未保存的更改，确定要切换吗？')) return
  isNew.value = false
  selectedName.value = name
  errorMsg.value = ''
  resetForm()

  try {
    const { content } = await readSkill(props.space, name)
    const parsed = parseSkillFile(content)
    if (parsed.ok && parsed.fields) {
      form.value = {
        name: parsed.fields.name,
        description: parsed.fields.description,
        license: parsed.fields.license ?? '',
        compatibility: parsed.fields.compatibility ?? '',
        body: parsed.fields.body,
      }
      if (parsed.fields.license || parsed.fields.compatibility) {
        showAdvanced.value = true
      }
    } else {
      // 结构化解析失败，退回原始文本编辑模式
      rawMode.value = true
      rawContent.value = content
      parseWarning.value = `原始文件未通过结构化解析（${parsed.error ?? '未知错误'}），已切换到原始编辑模式。`
    }
    dirty.value = false
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  }
}

function startNew() {
  if (dirty.value && !confirm('有未保存的更改，确定要新建吗？')) return
  isNew.value = true
  selectedName.value = null
  errorMsg.value = ''
  resetForm()
  form.value.body = '# 技能说明\n\n'
}

function switchToStructured() {
  // 从原始模式切回结构化：尝试重新解析
  const parsed = parseSkillFile(rawContent.value)
  if (parsed.ok && parsed.fields) {
    form.value = {
      name: parsed.fields.name,
      description: parsed.fields.description,
      license: parsed.fields.license ?? '',
      compatibility: parsed.fields.compatibility ?? '',
      body: parsed.fields.body,
    }
    rawMode.value = false
    parseWarning.value = ''
  } else {
    parseWarning.value = `仍无法解析：${parsed.error ?? '未知错误'}`
  }
}

watch(
  () => [form.value.name, form.value.description, form.value.license, form.value.compatibility, form.value.body, rawContent.value],
  () => { dirty.value = true },
  { deep: false },
)

async function save() {
  errorMsg.value = ''

  let content: string
  let name: string

  if (rawMode.value) {
    // 原始模式：保存前仍然校验 frontmatter 合法
    const parsed = parseSkillFile(rawContent.value)
    if (!parsed.ok) {
      errorMsg.value = `保存被拦截：${parsed.error ?? 'frontmatter 不合法'}`
      return
    }
    name = parsed.fields!.name
    if (isNew.value) {
      const nameErr = validateSkillName(name)
      if (nameErr) {
        errorMsg.value = `frontmatter.name 不合法：${nameErr}`
        return
      }
    }
    content = rawContent.value
  } else {
    if (isNew.value && nameError.value) {
      errorMsg.value = nameError.value
      return
    }
    if (descriptionError.value) {
      errorMsg.value = descriptionError.value
      return
    }
    name = isNew.value ? form.value.name.trim() : selectedName.value!
    // 重命名现有技能需要先删后建。本次保持简单：只允许新建时设置名称
    content = buildSkillFile({
      name,
      description: form.value.description.trim(),
      license: form.value.license?.trim() || undefined,
      compatibility: form.value.compatibility?.trim() || undefined,
      body: form.value.body,
    })
  }

  saving.value = true
  try {
    await writeSkill(props.space, name, content)
    dirty.value = false
    await loadSkills()
    selectedName.value = name
    isNew.value = false
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!selectedName.value) return
  if (!confirm(`确定要删除技能 "${selectedName.value}" 吗？此操作不可撤销。`)) return
  deleting.value = true
  errorMsg.value = ''
  try {
    await deleteSkill(props.space, selectedName.value)
    selectedName.value = null
    resetForm()
    await loadSkills()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    deleting.value = false
  }
}

const canPublish = computed(() => props.space.kind === 'user' && !isNew.value && !!selectedName.value && !dirty.value)

async function publishToCommunity() {
  if (!canPublish.value || !selectedName.value) return
  if (!confirm(`将 "${selectedName.value}" 发布到社区，让所有用户可见并下载？`)) return

  publishing.value = true
  errorMsg.value = ''
  publishMsg.value = ''
  try {
    let bodyMd: string
    if (rawMode.value) {
      bodyMd = rawContent.value
    } else {
      bodyMd = buildSkillFile({
        name: form.value.name,
        description: form.value.description.trim(),
        license: form.value.license?.trim() || undefined,
        compatibility: form.value.compatibility?.trim() || undefined,
        body: form.value.body,
      })
    }
    const published = await publishCommunitySkill(bodyMd)
    publishMsg.value = `已发布到社区：${published.name}`
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    publishing.value = false
  }
}

function handleClose() {
  if (dirty.value && !confirm('有未保存的更改，确定要关闭吗？')) return
  emit('close')
}

onMounted(async () => {
  await loadSkills()
  if (props.initialSkill) await selectSkill(props.initialSkill)
})
</script>

<template>
  <div class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40" @click.self="handleClose">
    <div class="flex h-[640px] w-[880px] max-w-[95vw] flex-col rounded-xl bg-white shadow-xl">
      <!-- 标题栏 -->
      <div class="flex h-14 flex-shrink-0 items-center justify-between border-b border-[#e5e7eb] px-5">
        <span class="font-semibold text-[#1f2937]">{{ title }}</span>
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

      <div class="flex min-h-0 flex-1">
        <!-- 左栏：列表 -->
        <div class="flex w-52 flex-shrink-0 flex-col border-r border-[#e5e7eb]">
          <div class="flex-1 overflow-y-auto p-2">
            <div v-if="loading" class="px-3 py-4 text-sm text-[#9ca3af]">加载中...</div>
            <div v-else-if="skills.length === 0" class="px-3 py-4 text-sm text-[#9ca3af]">暂无技能</div>
            <button
              v-for="skill in skills"
              :key="skill.name"
              :class="[
                'w-full rounded-md px-3 py-2 text-left transition-colors',
                selectedName === skill.name && !isNew
                  ? 'bg-[#e6f4ee] text-[#1f6f5b]'
                  : 'text-[#374151] hover:bg-[#f3f4f6]',
              ]"
              type="button"
              @click="selectSkill(skill.name)"
            >
              <div class="truncate text-sm font-medium">{{ skill.name }}</div>
              <div class="truncate text-xs text-[#9ca3af]">{{ skill.description || '无描述' }}</div>
            </button>
          </div>
          <div class="border-t border-[#e5e7eb] p-2">
            <button
              :class="[
                'flex w-full items-center gap-1.5 rounded-md px-3 py-2 text-sm transition-colors',
                isNew ? 'bg-[#e6f4ee] text-[#1f6f5b]' : 'text-[#374151] hover:bg-[#f3f4f6]',
              ]"
              type="button"
              @click="startNew"
            >
              <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
              </svg>
              新建技能
            </button>
          </div>
        </div>

        <!-- 右栏：编辑器 -->
        <div class="flex min-w-0 flex-1 flex-col">
          <div v-if="!selectedName && !isNew" class="flex flex-1 items-center justify-center text-sm text-[#9ca3af]">
            从左侧选择技能或新建
          </div>

          <template v-else>
            <!-- 可滚动的表单内容区 -->
            <div class="min-h-0 flex-1 overflow-y-auto px-5 pt-5">
              <!-- 结构化表单 -->
              <template v-if="!rawMode">
                <!-- 名称 -->
                <div class="mb-4">
                  <label class="mb-1 block text-xs font-medium text-[#6b7280]">技能名称</label>
                  <input
                    v-if="isNew"
                    v-model="form.name"
                    class="h-9 w-full rounded-md border border-[#d1d5db] px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                    placeholder="my-skill-name（小写字母、数字、连字符）"
                    type="text"
                  />
                  <div v-else class="flex h-9 items-center rounded-md bg-[#f9fafb] px-3 text-sm text-[#374151]">
                    {{ form.name }}
                  </div>
                  <p v-if="nameError" class="mt-1 text-xs text-[#9a3412]">{{ nameError }}</p>
                </div>

                <!-- 描述 -->
                <div class="mb-4">
                  <div class="mb-1 flex items-baseline justify-between">
                    <label class="block text-xs font-medium text-[#6b7280]">
                      描述 <span class="text-[#9a3412]">*</span>
                    </label>
                    <span
                      :class="[
                        'text-[10px] tabular-nums',
                        form.description.length > DESCRIPTION_MAX ? 'text-[#9a3412]' : 'text-[#9ca3af]',
                      ]"
                    >
                      {{ form.description.length }} / {{ DESCRIPTION_MAX }}
                    </span>
                  </div>
                  <textarea
                    v-model="form.description"
                    :maxlength="DESCRIPTION_MAX"
                    class="w-full resize-y rounded-md border border-[#d1d5db] p-2.5 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                    placeholder="模型会看到这段描述来判断何时使用该技能。写清楚触发场景和能力边界。"
                    rows="2"
                  />
                  <p v-if="descriptionError" class="mt-1 text-xs text-[#9a3412]">{{ descriptionError }}</p>
                </div>

                <!-- 高级字段（可折叠） -->
                <div class="mb-4">
                  <button
                    class="flex items-center gap-1 text-xs font-medium text-[#6b7280] hover:text-[#1f2937]"
                    type="button"
                    @click="showAdvanced = !showAdvanced"
                  >
                    <svg
                      :class="['h-3 w-3 transition-transform', showAdvanced ? 'rotate-90' : '']"
                      aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7" />
                    </svg>
                    高级字段（可选）
                  </button>
                  <div v-if="showAdvanced" class="mt-2 grid grid-cols-2 gap-3">
                    <label class="block">
                      <span class="mb-1 block text-xs text-[#6b7280]">license</span>
                      <input
                        v-model="form.license"
                        class="h-9 w-full rounded-md border border-[#d1d5db] px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                        placeholder="例如 MIT"
                        type="text"
                      />
                    </label>
                    <label class="block">
                      <div class="mb-1 flex items-baseline justify-between">
                        <span class="block text-xs text-[#6b7280]">compatibility</span>
                        <span
                          :class="[
                            'text-[10px] tabular-nums',
                            (form.compatibility ?? '').length > COMPATIBILITY_MAX ? 'text-[#9a3412]' : 'text-[#9ca3af]',
                          ]"
                        >
                          {{ (form.compatibility ?? '').length }} / {{ COMPATIBILITY_MAX }}
                        </span>
                      </div>
                      <input
                        v-model="form.compatibility"
                        :maxlength="COMPATIBILITY_MAX"
                        class="h-9 w-full rounded-md border border-[#d1d5db] px-3 text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                        placeholder="兼容性说明"
                        type="text"
                      />
                      <p v-if="compatibilityError" class="mt-1 text-xs text-[#9a3412]">{{ compatibilityError }}</p>
                    </label>
                  </div>
                </div>

                <!-- 技能正文 -->
                <div class="mb-5">
                  <div class="mb-1 flex items-baseline justify-between">
                    <label class="block text-xs font-medium text-[#6b7280]">技能内容（Markdown）</label>
                    <span class="text-[10px] tabular-nums text-[#9ca3af]">
                      {{ bodyCharCount.toLocaleString() }} 字符 · {{ bodyLineCount }} 行
                    </span>
                  </div>
                  <textarea
                    v-model="form.body"
                    class="w-full resize-y rounded-md border border-[#d1d5db] p-3 font-mono text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                    style="min-height: 220px"
                    placeholder="# 技能说明&#10;&#10;详细说明技能的功能、用法、示例..."
                    spellcheck="false"
                  />
                  <p class="mt-1 text-[10px] text-[#9ca3af]">前端会自动生成合法的 frontmatter（name/description 等），你无需手动写 `---` 分隔块。</p>
                </div>
              </template>

              <!-- 原始编辑模式（当文件无法被结构化解析时的兜底） -->
              <template v-else>
                <div class="mb-3 flex items-center justify-between">
                  <span class="text-xs font-medium text-[#6b7280]">原始 SKILL.md 编辑</span>
                  <button
                    class="text-xs text-[#1f6f5b] hover:underline"
                    type="button"
                    @click="switchToStructured"
                  >
                    尝试切换到结构化表单
                  </button>
                </div>
                <p class="mb-3 rounded-md border border-[#fcd34d] bg-[#fffbeb] px-3 py-2 text-xs text-[#92400e]">
                  {{ parseWarning }}
                </p>
                <textarea
                  v-model="rawContent"
                  class="w-full resize-y rounded-md border border-[#d1d5db] p-3 font-mono text-sm outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
                  style="min-height: 320px"
                  spellcheck="false"
                />
              </template>
            </div>

            <!-- 固定底部操作栏 -->
            <div class="flex-shrink-0 border-t border-[#e5e7eb] bg-white px-5 py-3">
              <p v-if="errorMsg" class="mb-2 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-xs text-[#9a3412]">
                {{ errorMsg }}
              </p>
              <p v-if="publishMsg" class="mb-2 rounded-md border border-[#bbf7d0] bg-[#f0fdf4] px-3 py-2 text-xs text-[#166534]">
                {{ publishMsg }}
              </p>
              <div class="flex items-center justify-between">
                <button
                  v-if="!isNew && selectedName"
                  class="rounded-md px-3 py-1.5 text-sm text-[#9a3412] transition hover:bg-[#fff7ed] disabled:opacity-50"
                  :disabled="deleting"
                  type="button"
                  @click="remove"
                >
                  {{ deleting ? '删除中...' : '删除' }}
                </button>
                <div v-else />
                <div class="flex items-center gap-2">
                  <button
                    v-if="canPublish"
                    class="rounded-md border border-[#1f6f5b] px-3 py-1.5 text-sm text-[#1f6f5b] transition hover:bg-[#e6f4ee] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="publishing"
                    type="button"
                    title="把当前技能发布到社区"
                    @click="publishToCommunity"
                  >
                    {{ publishing ? '发布中...' : '发布到社区' }}
                  </button>
                  <button
                    class="rounded-md bg-[#1f2937] px-4 py-1.5 text-sm text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]"
                    :disabled="!canSave"
                    type="button"
                    @click="save"
                  >
                    {{ saving ? '保存中...' : '保存' }}
                  </button>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
