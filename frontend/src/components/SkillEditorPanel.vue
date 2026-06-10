<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, watch, nextTick } from 'vue'
import {
  type FileSpace,
  type SkillFields,
  type SkillResourceDir,
  type SkillTreeEntry,
  SKILL_RESOURCE_DIRS,
  buildSkillFile,
  createSkillDirectory,
  createSkillFile,
  deleteSkillFile,
  listSkillTree,
  parseSkillFile,
  readSkill,
  readSkillFile,
  skillFileEditorKind,
  validatePlainSkillFileContent,
  validateSkillRelativePath,
  writeSkill,
  writeSkillFile,
} from '../skills'
import { getErrorMessage, publishCommunitySkill } from '../api'
import {
  SKILL_COMPATIBILITY_MAX,
  SKILL_DESCRIPTION_MAX,
  SKILL_DISPLAY_NAME_MAX,
} from '../config'
import { confirmDanger, confirmWarning } from '../composables/useConfirmDialog'

const props = defineProps<{
  space: FileSpace
  skillName: string
  displayName: string
}>()

const emit = defineEmits<{
  close: []
}>()

const tree = ref<SkillTreeEntry[]>([])
const treeLoading = ref(false)
const fileLoading = ref(false)
const saving = ref(false)
const deletingFile = ref(false)
const publishing = ref(false)
const errorMsg = ref('')
const publishMsg = ref('')

const selectedName = ref(props.skillName)
const selectedPath = ref<string | null>('SKILL.md')
const cleanSnapshot = ref<string | null>(null)

const form = ref<SkillFields>({
  name: '',
  display_name: '',
  description: '',
  license: '',
  compatibility: '',
  body: '',
})
const showAdvanced = ref(false)
const rawMode = ref(false)
const rawContent = ref('')
const parseWarning = ref('')
const plainContent = ref('')

const descTextarea = ref<HTMLTextAreaElement | null>(null)
const bodyTextarea = ref<HTMLTextAreaElement | null>(null)
const rawTextarea = ref<HTMLTextAreaElement | null>(null)
const plainTextarea = ref<HTMLTextAreaElement | null>(null)

function autoGrow(el: HTMLTextAreaElement | null): void {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

watch(() => form.value.description, () => { nextTick(() => autoGrow(descTextarea.value)) })
watch(() => form.value.body, () => { nextTick(() => autoGrow(bodyTextarea.value)) })
watch(rawContent, () => { nextTick(() => autoGrow(rawTextarea.value)) })
watch(plainContent, () => { nextTick(() => autoGrow(plainTextarea.value)) })

watch(descTextarea, (el) => { if (el) autoGrow(el) })
watch(bodyTextarea, (el) => { if (el) autoGrow(el) })
watch(rawTextarea, (el) => { if (el) autoGrow(el) })
watch(plainTextarea, (el) => { if (el) autoGrow(el) })

const DESCRIPTION_MAX = SKILL_DESCRIPTION_MAX
const DISPLAY_NAME_MAX = SKILL_DISPLAY_NAME_MAX
const COMPATIBILITY_MAX = SKILL_COMPATIBILITY_MAX

const descriptionError = computed(() => {
  const d = form.value.description
  if (!d.trim()) return '描述不能为空（会作为技能对模型的说明）'
  if (d.length > DESCRIPTION_MAX) return `描述不能超过 ${DESCRIPTION_MAX} 字符（当前 ${d.length}）`
  return null
})

const displayNameError = computed(() => {
  const dn = form.value.display_name ?? ''
  if (dn.length > DISPLAY_NAME_MAX) return `展示名不能超过 ${DISPLAY_NAME_MAX} 字符（当前 ${dn.length}）`
  return null
})

const compatibilityError = computed(() => {
  const c = form.value.compatibility ?? ''
  if (c.length > COMPATIBILITY_MAX) return `compatibility 不能超过 ${COMPATIBILITY_MAX} 字符（当前 ${c.length}）`
  return null
})

const bodyCharCount = computed(() => form.value.body.length)
const bodyLineCount = computed(() => form.value.body.split('\n').length)
const plainCharCount = computed(() => plainContent.value.length)
const plainLineCount = computed(() => plainContent.value.split('\n').length)

const selectedEditorKind = computed(() => {
  if (selectedPath.value === 'SKILL.md') return 'skill'
  return selectedPath.value ? skillFileEditorKind(selectedPath.value) : null
})

const dirty = computed(() => cleanSnapshot.value !== null && editorSnapshot() !== cleanSnapshot.value)

const isImageFile = computed(() => {
  if (!selectedPath.value) return false
  const ext = selectedPath.value.slice(selectedPath.value.lastIndexOf('.')).toLowerCase()
  return ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'].includes(ext)
})

const canSave = computed(() => {
  if (saving.value || fileLoading.value) return false
  if (isImageFile.value) return false
  if (selectedEditorKind.value === 'skill') {
    if (rawMode.value) return rawContent.value.trim().length > 0
    if (displayNameError.value) return false
    if (descriptionError.value) return false
    if (compatibilityError.value) return false
    return true
  }
  return !!selectedName.value && !!selectedPath.value
})

const canPublish = computed(() =>
  props.space.kind === 'user'
  && !!selectedName.value
  && !dirty.value
  && selectedPath.value === 'SKILL.md',
)

function markClean(): void { cleanSnapshot.value = editorSnapshot() }

function resetEditor(): void {
  form.value = { name: '', display_name: '', description: '', license: '', compatibility: '', body: '' }
  showAdvanced.value = false
  rawMode.value = false
  rawContent.value = ''
  parseWarning.value = ''
  plainContent.value = ''
  markClean()
}

async function confirmDiscard(message = '有未保存的更改，确定要切换吗？'): Promise<boolean> {
  return !dirty.value || await confirmWarning({
    title: '未保存的更改',
    message,
    confirmText: '继续',
  })
}

async function loadTree(name: string): Promise<void> {
  treeLoading.value = true
  try {
    tree.value = await listSkillTree(props.space, name)
  } catch (e) {
    tree.value = []
    errorMsg.value = getErrorMessage(e)
  } finally {
    treeLoading.value = false
  }
}

function loadSkillForm(content: string, folderName: string): void {
  const parsed = parseSkillFile(content)
  if (parsed.ok && parsed.fields) {
    form.value = {
      name: parsed.fields.name,
      display_name: parsed.fields.display_name ?? '',
      description: parsed.fields.description,
      license: parsed.fields.license ?? '',
      compatibility: parsed.fields.compatibility ?? '',
      body: parsed.fields.body,
    }
    rawMode.value = false
    rawContent.value = ''
    parseWarning.value = parsed.fields.name !== folderName
      ? 'SKILL.md frontmatter.name 与技能文件夹名不一致，保存时会按文件夹名写回。'
      : ''
    showAdvanced.value = !!(parsed.fields.license || parsed.fields.compatibility)
  } else {
    rawMode.value = true
    rawContent.value = content
    parseWarning.value = `原始文件未通过结构化解析（${parsed.error ?? '未知错误'}），已切换到原始编辑模式。`
  }
  markClean()
}

async function openFile(relPath: string, askBeforeSwitch = true): Promise<void> {
  if (!selectedName.value) return
  if (askBeforeSwitch && !await confirmDiscard()) return
  const pathError = validateSkillRelativePath(relPath, true)
  if (pathError) {
    errorMsg.value = pathError
    return
  }
  const entry = tree.value.find((item) => item.relPath === relPath)
  if (entry?.isDir) return

  fileLoading.value = true
  errorMsg.value = ''
  selectedPath.value = relPath
  resetEditor()
  try {
    if (relPath === 'SKILL.md') {
      const { content } = await readSkill(props.space, selectedName.value)
      loadSkillForm(content, selectedName.value)
    } else if (isImageFile.value) {
      plainContent.value = ''
      markClean()
    } else {
      const { content } = await readSkillFile(props.space, selectedName.value, relPath)
      plainContent.value = content
      markClean()
    }
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    fileLoading.value = false
  }
}

function switchToStructured(): void {
  const parsed = parseSkillFile(rawContent.value)
  if (parsed.ok && parsed.fields) {
    form.value = {
      name: selectedName.value ?? parsed.fields.name,
      display_name: parsed.fields.display_name ?? '',
      description: parsed.fields.description,
      license: parsed.fields.license ?? '',
      compatibility: parsed.fields.compatibility ?? '',
      body: parsed.fields.body,
    }
    rawMode.value = false
    parseWarning.value = ''
    showAdvanced.value = !!(parsed.fields.license || parsed.fields.compatibility)
  } else {
    parseWarning.value = `仍无法解析：${parsed.error ?? '未知错误'}`
  }
}

function structuredSkillContent(name: string): string {
  return buildSkillFile({
    name,
    display_name: form.value.display_name?.trim() || undefined,
    description: form.value.description.trim(),
    license: form.value.license?.trim() || undefined,
    compatibility: form.value.compatibility?.trim() || undefined,
    body: form.value.body,
  })
}

function editorSnapshot(): string {
  if (selectedEditorKind.value === 'skill') {
    if (rawMode.value) {
      return JSON.stringify({ kind: 'skill-raw', content: rawContent.value })
    }
    return JSON.stringify({
      kind: 'skill-structured',
      name: selectedName.value ?? form.value.name,
      display_name: form.value.display_name ?? '',
      description: form.value.description,
      license: form.value.license ?? '',
      compatibility: form.value.compatibility ?? '',
      body: form.value.body,
    })
  }
  if (selectedEditorKind.value) {
    return JSON.stringify({ kind: selectedEditorKind.value, path: selectedPath.value, content: plainContent.value })
  }
  return JSON.stringify({ kind: 'none' })
}

async function saveSkillFile(): Promise<boolean> {
  if (!selectedName.value || !selectedPath.value) return false
  let content: string
  if (rawMode.value) {
    const parsed = parseSkillFile(rawContent.value)
    if (!parsed.ok) { errorMsg.value = `保存被拦截：${parsed.error ?? 'frontmatter 不合法'}`; return false }
    if (parsed.fields!.name !== selectedName.value) { errorMsg.value = 'SKILL.md frontmatter.name 必须与技能文件夹名一致。'; return false }
    content = rawContent.value
  } else {
    if (descriptionError.value) { errorMsg.value = descriptionError.value; return false }
    if (displayNameError.value) { errorMsg.value = displayNameError.value; return false }
    if (compatibilityError.value) { errorMsg.value = compatibilityError.value; return false }
    content = structuredSkillContent(selectedName.value)
  }
  await writeSkill(props.space, selectedName.value, content)
  return true
}

async function savePlainFile(): Promise<boolean> {
  if (!selectedName.value || !selectedPath.value) return false
  const contentError = validatePlainSkillFileContent(selectedPath.value, plainContent.value)
  if (contentError) { errorMsg.value = contentError; return false }
  await writeSkillFile(props.space, selectedName.value, selectedPath.value, plainContent.value)
  return true
}

async function save(): Promise<void> {
  errorMsg.value = ''
  publishMsg.value = ''
  saving.value = true
  try {
    if (selectedEditorKind.value === 'skill') {
      const saved = await saveSkillFile()
      if (!saved) return
      if (selectedName.value) await loadTree(selectedName.value)
      markClean()
    } else {
      const saved = await savePlainFile()
      if (!saved) return
      if (selectedName.value) await loadTree(selectedName.value)
      markClean()
    }
    publishMsg.value = '保存成功'
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    saving.value = false
  }
}

async function removeFile(relPath: string): Promise<void> {
  if (!selectedName.value || relPath === 'SKILL.md') return
  const confirmed = await confirmDanger({
    title: '删除文件',
    message: `确定要删除文件 "${relPath}" 吗？此操作不可撤销。`,
    confirmText: '删除',
  })
  if (!confirmed) return
  deletingFile.value = true
  errorMsg.value = ''
  publishMsg.value = ''
  try {
    await deleteSkillFile(props.space, selectedName.value, relPath)
    await loadTree(selectedName.value)
    if (selectedPath.value === relPath) await openFile('SKILL.md', false)
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    deletingFile.value = false
  }
}

function askTargetFolder(defaultFolder: '' | SkillResourceDir = ''): '' | SkillResourceDir | null {
  const raw = prompt('目标文件夹：留空表示技能根目录，或输入 references / assets / examples / templates', defaultFolder)
  if (raw === null) return null
  const value = raw.trim()
  if (value === '') return ''
  if ((SKILL_RESOURCE_DIRS as readonly string[]).includes(value)) return value as SkillResourceDir
  errorMsg.value = '只能使用 references、assets、examples 或 templates 文件夹。'
  return null
}

async function addFile(defaultFolder: '' | SkillResourceDir = ''): Promise<void> {
  if (!selectedName.value) return
  if (!await confirmDiscard()) return
  errorMsg.value = ''
  publishMsg.value = ''
  const folder = askTargetFolder(defaultFolder)
  if (folder === null) return
  const filename = prompt('文件名（支持 md、txt、json、yaml、yml）')
  if (filename === null) return
  const safeName = filename.trim()
  const relPath = folder ? `${folder}/${safeName}` : safeName
  const pathError = validateSkillRelativePath(relPath)
  if (pathError) { errorMsg.value = pathError; return }
  if (tree.value.some((entry) => entry.relPath === relPath)) { errorMsg.value = `文件 ${relPath} 已存在。`; return }
  try {
    await createSkillFile(props.space, selectedName.value, relPath)
    await loadTree(selectedName.value)
    await openFile(relPath, false)
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  }
}

async function addFolder(): Promise<void> {
  if (!selectedName.value) return
  errorMsg.value = ''
  publishMsg.value = ''
  const raw = prompt('文件夹名（只能是 references、assets、examples 或 templates）')
  if (raw === null) return
  const name = raw.trim()
  if (!(SKILL_RESOURCE_DIRS as readonly string[]).includes(name)) {
    errorMsg.value = '只能新建 references、assets、examples 或 templates 文件夹。'
    return
  }
  try {
    await createSkillDirectory(props.space, selectedName.value, name as SkillResourceDir)
    await loadTree(selectedName.value)
    publishMsg.value = `已创建 ${name}/`
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  }
}

async function publishToCommunity(): Promise<void> {
  if (!canPublish.value || !selectedName.value) return
  const confirmed = await confirmWarning({
    title: '发布到社区',
    message: `将 "${selectedName.value}" 发布到社区，让所有用户可见并下载？`,
    confirmText: '发布',
  })
  if (!confirmed) return
  publishing.value = true
  errorMsg.value = ''
  publishMsg.value = ''
  try {
    const published = await publishCommunitySkill(selectedName.value)
    publishMsg.value = `已发布到社区：${published.display_name || published.name}`
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    publishing.value = false
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key.toLowerCase() !== 's' || (!event.ctrlKey && !event.metaKey) || event.altKey) return
  event.preventDefault()
  if (!canSave.value) return
  void save()
}

onMounted(async () => {
  document.addEventListener('keydown', handleKeydown)
  await loadTree(props.skillName)
  await openFile('SKILL.md', false)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="flex h-full flex-col bg-white pt-14">
    <!-- 主体：文件树 + 编辑器 -->
    <div class="flex min-h-0 flex-1">
      <!-- 文件树 -->
      <div class="flex w-52 flex-shrink-0 flex-col bg-white border-r border-[#e5e7eb]">
        <div class="flex h-10 items-center justify-between px-2.5 flex-shrink-0">
          <span class="truncate text-xs font-semibold text-[#1f2937]">{{ selectedName }}</span>
          <div class="flex items-center gap-0.5">
            <button
              class="flex h-6 w-6 items-center justify-center rounded-md text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#4b5563] transition-colors"
              title="新建文件"
              type="button"
              @click="addFile('')"
            >
              <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
              </svg>
            </button>
            <button
              class="flex h-6 w-6 items-center justify-center rounded-md text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#4b5563] transition-colors"
              title="新建文件夹"
              type="button"
              @click="addFolder"
            >
              <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m3-3H9m-3 7h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7l-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2Z" />
              </svg>
            </button>
          </div>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto p-1.5 space-y-0.5">
          <div v-if="treeLoading" class="px-2.5 py-3 text-xs text-[#9ca3af]">加载文件...</div>
          <template v-else>
            <template v-for="entry in tree" :key="entry.relPath">
              <div
                v-if="entry.isDir"
                class="group mt-1 flex h-7 items-center justify-between rounded-lg px-2 text-xs text-[#4b5563] font-medium"
              >
                <div class="flex min-w-0 items-center gap-1.5">
                  <svg class="h-3.5 w-3.5 flex-shrink-0 text-[#9ca3af]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7h7l2 2h9v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
                  </svg>
                  <span class="truncate">{{ entry.name }}</span>
                  <span v-if="entry.virtual" class="text-[9px] text-[#9ca3af] font-normal scale-95">virtual</span>
                </div>
                <button
                  class="flex h-5 w-5 items-center justify-center rounded text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#4b5563] transition-colors"
                  :title="`在 ${entry.name}/ 中新建文件`"
                  type="button"
                  @click.stop="addFile(entry.name as SkillResourceDir)"
                >
                  <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M12 5v14m7-7H5" />
                  </svg>
                </button>
              </div>
              <div
                v-else
                class="group relative flex w-full items-center justify-between rounded-lg transition-colors duration-150"
                :class="[
                  selectedPath === entry.relPath
                    ? 'bg-[#f3f4f6] text-[#1f2937] font-semibold'
                    : 'text-[#4b5563] hover:bg-[#f3f4f6]/40',
                ]"
              >
                <button
                  :class="[
                    'flex-1 min-w-0 flex h-7 items-center gap-1.5 px-2 text-left text-xs transition-colors duration-150 rounded-lg',
                    entry.parent ? 'pl-7' : '',
                  ]"
                  type="button"
                  @click="openFile(entry.relPath)"
                >
                  <svg class="h-3.5 w-3.5 flex-shrink-0 text-[#9ca3af]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 3h7l5 5v13H7V3Z" />
                  </svg>
                  <span class="truncate">{{ entry.name }}</span>
                </button>
                <button
                  v-if="entry.relPath !== 'SKILL.md'"
                  class="mr-1.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md text-[#9ca3af] hover:bg-red-50 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-all duration-150"
                  title="删除文件"
                  type="button"
                  @click.stop="removeFile(entry.relPath)"
                >
                  <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </template>
          </template>
        </div>
      </div>

      <!-- 编辑器 -->
      <div class="flex min-w-0 flex-1 flex-col">
        <!-- Scroll Area Wrapper -->
        <div class="relative min-h-0 flex-1">
          <div class="h-full overflow-y-auto px-5 pt-3 flex flex-col" :class="dirty ? 'pb-16' : 'pb-4'">
            <div v-if="fileLoading" class="py-10 text-center text-sm text-[#9ca3af]">加载文件...</div>

            <div v-else class="space-y-6 flex-1 flex flex-col">
              <template v-if="selectedEditorKind === 'skill'">
                <template v-if="!rawMode">
                  <div class="mb-3.5">
                    <label class="mb-1 block text-xs font-medium text-[#4b5563]">技能名称</label>
                    <div class="flex h-9 items-center rounded-xl border border-[#d1d5db] bg-[#f3f4f6] px-3 text-xs font-medium text-[#1f2937]">
                      {{ selectedName }}
                    </div>
                    <p v-if="parseWarning" class="mt-1 text-xs text-[#92400e]">{{ parseWarning }}</p>
                  </div>

                  <div class="mb-3.5">
                    <div class="mb-1 flex items-baseline justify-between">
                      <label class="block text-xs font-medium text-[#4b5563]">展示名</label>
                      <span
                        :class="[
                          'text-[10px] tabular-nums',
                          (form.display_name ?? '').length > DISPLAY_NAME_MAX ? 'text-[#9a3412]' : 'text-[#9ca3af]',
                        ]"
                      >
                        {{ (form.display_name ?? '').length }} / {{ DISPLAY_NAME_MAX }}
                      </span>
                    </div>
                    <input
                      v-model="form.display_name"
                      :maxlength="DISPLAY_NAME_MAX"
                      class="h-9 w-full rounded-xl border border-[#d1d5db] bg-[#f3f4f6] px-3 text-xs outline-none transition duration-150 focus:bg-white focus:border-[#9ca3af] focus:ring-2 focus:ring-[#1f2937]/10"
                      placeholder="例如：数学解题助手"
                      type="text"
                    />
                    <p v-if="displayNameError" class="mt-1 text-xs text-[#9a3412]">{{ displayNameError }}</p>
                  </div>

                  <div class="mb-3.5">
                    <div class="mb-1 flex items-baseline justify-between">
                      <label class="block text-xs font-medium text-[#4b5563]">
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
                      ref="descTextarea"
                      v-model="form.description"
                      :maxlength="DESCRIPTION_MAX"
                      class="w-full resize-none overflow-hidden rounded-xl border border-[#d1d5db] bg-[#f3f4f6] p-2.5 text-xs outline-none transition duration-150 focus:bg-white focus:border-[#9ca3af] focus:ring-2 focus:ring-[#1f2937]/10"
                      rows="2"
                      @input="autoGrow($event.target as HTMLTextAreaElement)"
                    />
                    <p v-if="descriptionError" class="mt-1 text-xs text-[#9a3412]">{{ descriptionError }}</p>
                  </div>

                  <div class="mb-3.5">
                    <button
                      class="flex items-center gap-1 text-xs font-medium text-[#4b5563] hover:text-[#1f2937]"
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
                        <span class="mb-1 block text-xs text-[#4b5563]">license</span>
                        <input
                          v-model="form.license"
                          class="h-9 w-full rounded-xl border border-[#d1d5db] bg-[#f3f4f6] px-3 text-xs outline-none transition duration-150 focus:bg-white focus:border-[#9ca3af] focus:ring-2 focus:ring-[#1f2937]/10"
                          placeholder="例如 MIT"
                          type="text"
                        />
                      </label>
                      <label class="block">
                        <div class="mb-1 flex items-baseline justify-between">
                          <span class="block text-xs text-[#4b5563]">compatibility</span>
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
                          class="h-9 w-full rounded-xl border border-[#d1d5db] bg-[#f3f4f6] px-3 text-xs outline-none transition duration-150 focus:bg-white focus:border-[#9ca3af] focus:ring-2 focus:ring-[#1f2937]/10"
                          placeholder="兼容性说明"
                          type="text"
                        />
                        <p v-if="compatibilityError" class="mt-1 text-xs text-[#9a3412]">{{ compatibilityError }}</p>
                      </label>
                    </div>
                  </div>

                  <div class="mb-4 flex flex-col flex-1">
                    <div class="mb-1 flex items-baseline justify-between">
                      <label class="block text-xs font-medium text-[#4b5563]">技能内容（Markdown）</label>
                      <span class="text-[10px] tabular-nums text-[#9ca3af]">
                        {{ bodyCharCount.toLocaleString() }} 字符 · {{ bodyLineCount }} 行
                      </span>
                    </div>
                    <textarea
                      ref="bodyTextarea"
                      v-model="form.body"
                      class="w-full flex-1 resize-none overflow-hidden rounded-xl border border-[#d1d5db] bg-[#f3f4f6] p-3 font-mono text-xs outline-none transition duration-150 focus:bg-white focus:border-[#9ca3af] focus:ring-2 focus:ring-[#1f2937]/10"
                      spellcheck="false"
                      @input="autoGrow($event.target as HTMLTextAreaElement)"
                    />
                    <p class="mt-1 text-[10px] text-[#9ca3af]">前端会自动生成合法的 frontmatter（name/description 等），你无需手动写 `---` 分隔块。</p>
                  </div>
                </template>

                <template v-else>
                  <div class="mb-2 flex items-center justify-between">
                    <span class="text-xs font-medium text-[#4b5563]">原始 SKILL.md 编辑</span>
                    <button
                      class="text-xs font-semibold text-[#1f2937] hover:underline"
                      type="button"
                      @click="switchToStructured"
                    >
                      尝试切换到结构化表单
                    </button>
                  </div>
                  <p class="mb-3 rounded-xl bg-amber-50/70 border border-amber-200/50 px-3 py-2 text-xs text-amber-800">
                    {{ parseWarning }}
                  </p>
                  <textarea
                    ref="rawTextarea"
                    v-model="rawContent"
                    class="w-full flex-1 resize-none overflow-hidden rounded-xl border border-[#d1d5db] bg-[#f3f4f6] p-3 font-mono text-xs outline-none transition duration-150 focus:bg-white focus:border-[#9ca3af] focus:ring-2 focus:ring-[#1f2937]/10"
                    spellcheck="false"
                    @input="autoGrow($event.target as HTMLTextAreaElement)"
                  />
                </template>
              </template>

              <template v-else>
                <div v-if="isImageFile" class="flex flex-col items-center justify-center p-8 rounded-2xl bg-[#f3f4f6] border border-[#e5e7eb]" style="min-height: 540px">
                  <span class="text-3xl mb-2">🖼️</span>
                  <p class="text-xs text-[#4b5563] font-semibold">图片文件仅支持管理，无法直接编辑内容。</p>
                  <p class="text-[10px] text-[#9ca3af] mt-1">{{ selectedPath }}</p>
                </div>
                <template v-else>
                  <div class="mb-1 flex items-baseline justify-between">
                    <label class="block text-xs font-medium text-[#4b5563]">文本内容</label>
                    <span class="text-[10px] tabular-nums text-[#9ca3af]">
                      {{ plainCharCount.toLocaleString() }} 字符 · {{ plainLineCount }} 行
                    </span>
                  </div>
                  <textarea
                    ref="plainTextarea"
                    v-model="plainContent"
                    class="w-full flex-1 resize-none overflow-hidden rounded-xl border border-[#d1d5db] bg-[#f3f4f6] p-3 font-mono text-xs outline-none transition duration-150 focus:bg-white focus:border-[#9ca3af] focus:ring-2 focus:ring-[#1f2937]/10"
                    spellcheck="false"
                    @input="autoGrow($event.target as HTMLTextAreaElement)"
                  />
                </template>
              </template>

              <!-- 消息 / 发布按钮 -->
              <div v-if="canPublish || errorMsg || publishMsg" class="mt-4 pt-3.5 flex-shrink-0">
                <p v-if="errorMsg" class="mb-3 rounded-xl bg-rose-50/60 border border-rose-200/50 px-3 py-2 text-xs text-rose-800">
                  {{ errorMsg }}
                </p>
                <p v-if="publishMsg" class="mb-3 rounded-xl bg-emerald-50/60 border border-emerald-200/50 px-3 py-2 text-xs text-emerald-800">
                  {{ publishMsg }}
                </p>
                <div v-if="canPublish" class="flex items-center justify-end">
                  <button
                    class="rounded-xl bg-[#f3f4f6] px-3.5 py-1.5 text-xs text-[#4b5563] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] disabled:cursor-not-allowed disabled:opacity-50 active:scale-95"
                    :disabled="publishing"
                    type="button"
                    title="把当前技能发布到社区"
                    @click="publishToCommunity"
                  >
                    {{ publishing ? '发布中...' : '发布到社区' }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 悬浮保存按钮 -->
          <Transition name="fade">
            <button
              v-if="dirty"
              class="absolute bottom-6 right-8 z-30 flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-xl hover:bg-slate-800 active:scale-95 transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!canSave"
              type="button"
              @click="save"
            >
              <span v-if="saving" class="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <svg v-else class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
              </svg>
              <span>{{ saving ? '保存中...' : '保存修改' }}</span>
            </button>
          </Transition>
        </div>
      </div>
    </div>
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
