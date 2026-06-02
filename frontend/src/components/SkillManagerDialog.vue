<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, watch, nextTick } from 'vue'
import {
  type FileSpace,
  type SkillFields,
  type SkillMeta,
  type SkillResourceDir,
  type SkillTreeEntry,
  SKILL_RESOURCE_DIRS,
  buildSkillFile,
  createSkillDirectory,
  createSkillFile,
  deleteSkill,
  deleteSkillFile,
  listSkillTree,
  listSkills,
  parseSkillFile,
  readSkill,
  readSkillFile,
  skillFileEditorKind,
  validatePlainSkillFileContent,
  validateSkillName,
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

const props = defineProps<{
  space: FileSpace
  title: string
  initialSkill?: string
}>()

const emit = defineEmits<{
  close: []
}>()

const skills = ref<SkillMeta[]>([])
const tree = ref<SkillTreeEntry[]>([])
const loading = ref(false)
const treeLoading = ref(false)
const fileLoading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const deletingFile = ref(false)
const publishing = ref(false)
const errorMsg = ref('')
const publishMsg = ref('')

const selectedName = ref<string | null>(null)
const selectedPath = ref<string | null>(null)
const isNew = ref(false)
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

watch(() => form.value.description, () => {
  nextTick(() => autoGrow(descTextarea.value))
})
watch(() => form.value.body, () => {
  nextTick(() => autoGrow(bodyTextarea.value))
})
watch(rawContent, () => {
  nextTick(() => autoGrow(rawTextarea.value))
})
watch(plainContent, () => {
  nextTick(() => autoGrow(plainTextarea.value))
})

watch(descTextarea, (el) => {
  if (el) autoGrow(el)
})
watch(bodyTextarea, (el) => {
  if (el) autoGrow(el)
})
watch(rawTextarea, (el) => {
  if (el) autoGrow(el)
})
watch(plainTextarea, (el) => {
  if (el) autoGrow(el)
})

const DESCRIPTION_MAX = SKILL_DESCRIPTION_MAX
const DISPLAY_NAME_MAX = SKILL_DISPLAY_NAME_MAX
const COMPATIBILITY_MAX = SKILL_COMPATIBILITY_MAX

const nameError = computed(() => {
  if (!isNew.value) return null
  return validateSkillName(form.value.name)
})

const descriptionError = computed(() => {
  const d = form.value.description
  if (!d.trim()) return '描述不能为空（会作为技能对模型的说明）'
  if (d.length > DESCRIPTION_MAX) return `描述不能超过 ${DESCRIPTION_MAX} 字符（当前 ${d.length}）`
  return null
})

const displayNameError = computed(() => {
  const displayName = form.value.display_name ?? ''
  if (displayName.length > DISPLAY_NAME_MAX) return `展示名不能超过 ${DISPLAY_NAME_MAX} 字符（当前 ${displayName.length}）`
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

const currentEntry = computed(() => tree.value.find((entry) => entry.relPath === selectedPath.value) ?? null)
const selectedEditorKind = computed(() => {
  if (isNew.value || selectedPath.value === 'SKILL.md') return 'skill'
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
    if (isNew.value && nameError.value) return false
    if (displayNameError.value) return false
    if (descriptionError.value) return false
    if (compatibilityError.value) return false
    return true
  }
  return !!selectedName.value && !!selectedPath.value && currentEntry.value?.isDir !== true
})

const canPublish = computed(() =>
  props.space.kind === 'user'
  && !isNew.value
  && !!selectedName.value
  && !dirty.value
  && selectedPath.value === 'SKILL.md',
)

function markClean(): void {
  cleanSnapshot.value = editorSnapshot()
}

function resetEditor(): void {
  form.value = { name: '', display_name: '', description: '', license: '', compatibility: '', body: '' }
  showAdvanced.value = false
  rawMode.value = false
  rawContent.value = ''
  parseWarning.value = ''
  plainContent.value = ''
  markClean()
}

function confirmDiscard(message = '有未保存的更改，确定要切换吗？'): boolean {
  return !dirty.value || confirm(message)
}

async function loadSkills(): Promise<void> {
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
  if (askBeforeSwitch && !confirmDiscard()) return
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

async function selectSkill(name: string): Promise<void> {
  if (!confirmDiscard()) return
  isNew.value = false
  selectedName.value = name
  selectedPath.value = 'SKILL.md'
  errorMsg.value = ''
  publishMsg.value = ''
  resetEditor()
  await loadTree(name)
  await openFile('SKILL.md', false)
}

function startNew(): void {
  if (!confirmDiscard('有未保存的更改，确定要新建吗？')) return
  isNew.value = true
  selectedName.value = null
  selectedPath.value = null
  tree.value = []
  errorMsg.value = ''
  publishMsg.value = ''
  resetEditor()
  form.value.body = '# 技能说明\n\n'
  markClean()
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
      return JSON.stringify({
        kind: 'skill-raw',
        content: rawContent.value,
      })
    }
    return JSON.stringify({
      kind: 'skill-structured',
      name: isNew.value ? form.value.name : (selectedName.value ?? form.value.name),
      display_name: form.value.display_name ?? '',
      description: form.value.description,
      license: form.value.license ?? '',
      compatibility: form.value.compatibility ?? '',
      body: form.value.body,
    })
  }

  if (selectedEditorKind.value) {
    return JSON.stringify({
      kind: selectedEditorKind.value,
      path: selectedPath.value,
      content: plainContent.value,
    })
  }

  return JSON.stringify({ kind: 'none' })
}

async function saveSkillFile(): Promise<boolean> {
  if (!selectedName.value || !selectedPath.value) return false

  let content: string
  if (rawMode.value) {
    const parsed = parseSkillFile(rawContent.value)
    if (!parsed.ok) {
      errorMsg.value = `保存被拦截：${parsed.error ?? 'frontmatter 不合法'}`
      return false
    }
    if (parsed.fields!.name !== selectedName.value) {
      errorMsg.value = 'SKILL.md frontmatter.name 必须与技能文件夹名一致。'
      return false
    }
    content = rawContent.value
  } else {
    if (descriptionError.value) {
      errorMsg.value = descriptionError.value
      return false
    }
    if (displayNameError.value) {
      errorMsg.value = displayNameError.value
      return false
    }
    if (compatibilityError.value) {
      errorMsg.value = compatibilityError.value
      return false
    }
    content = structuredSkillContent(selectedName.value)
  }

  await writeSkill(props.space, selectedName.value, content)
  return true
}

async function savePlainFile(): Promise<boolean> {
  if (!selectedName.value || !selectedPath.value) return false
  const contentError = validatePlainSkillFileContent(selectedPath.value, plainContent.value)
  if (contentError) {
    errorMsg.value = contentError
    return false
  }
  await writeSkillFile(props.space, selectedName.value, selectedPath.value, plainContent.value)
  return true
}

async function save(): Promise<void> {
  errorMsg.value = ''
  publishMsg.value = ''

  if (isNew.value) {
    if (nameError.value) {
      errorMsg.value = nameError.value
      return
    }
    if (descriptionError.value) {
      errorMsg.value = descriptionError.value
      return
    }
    if (displayNameError.value) {
      errorMsg.value = displayNameError.value
      return
    }
  }

  saving.value = true
  try {
    if (isNew.value) {
      const name = form.value.name.trim()
      await writeSkill(props.space, name, structuredSkillContent(name))
      selectedName.value = name
      selectedPath.value = 'SKILL.md'
      isNew.value = false
      await loadSkills()
      await loadTree(name)
      markClean()
    } else if (selectedEditorKind.value === 'skill') {
      const saved = await saveSkillFile()
      if (!saved) return
      if (selectedName.value) {
        await loadSkills()
        await loadTree(selectedName.value)
      }
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

async function remove(skillName?: string): Promise<void> {
  const targetName = skillName || selectedName.value
  if (!targetName) return
  if (!confirm(`确定要删除技能 "${targetName}" 吗？此操作不可撤销。`)) return
  deleting.value = true
  errorMsg.value = ''
  publishMsg.value = ''
  try {
    await deleteSkill(props.space, targetName)
    if (selectedName.value === targetName) {
      selectedName.value = null
      selectedPath.value = null
      tree.value = []
      resetEditor()
    }
    await loadSkills()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    deleting.value = false
  }
}

async function removeFile(relPath: string): Promise<void> {
  if (!selectedName.value || relPath === 'SKILL.md') return
  if (!confirm(`确定要删除文件 "${relPath}" 吗？此操作不可撤销。`)) return
  deletingFile.value = true
  errorMsg.value = ''
  publishMsg.value = ''
  try {
    await deleteSkillFile(props.space, selectedName.value, relPath)
    await loadTree(selectedName.value)
    if (selectedPath.value === relPath) {
      await openFile('SKILL.md', false)
    }
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
  if (!confirmDiscard()) return
  errorMsg.value = ''
  publishMsg.value = ''
  const folder = askTargetFolder(defaultFolder)
  if (folder === null) return
  const filename = prompt('文件名（支持 md、txt、json、yaml、yml）')
  if (filename === null) return
  const safeName = filename.trim()
  const relPath = folder ? `${folder}/${safeName}` : safeName
  const pathError = validateSkillRelativePath(relPath)
  if (pathError) {
    errorMsg.value = pathError
    return
  }
  if (tree.value.some((entry) => entry.relPath === relPath)) {
    errorMsg.value = `文件 ${relPath} 已存在。`
    return
  }
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
  if (!confirm(`将 "${selectedName.value}" 发布到社区，让所有用户可见并下载？`)) return

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

function handleClose(): void {
  if (!confirmDiscard('有未保存的更改，确定要关闭吗？')) return
  emit('close')
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key.toLowerCase() !== 's' || (!event.ctrlKey && !event.metaKey) || event.altKey) return
  event.preventDefault()
  if (!canSave.value) return
  void save()
}

onMounted(async () => {
  document.addEventListener('keydown', handleKeydown)
  await loadSkills()
  if (props.initialSkill) await selectSkill(props.initialSkill)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 backdrop-blur-sm" @click.self="handleClose">
    <div class="modal-card flex h-[680px] w-[1080px] max-w-[96vw] flex-col rounded-2xl bg-white shadow-xl overflow-hidden">
      <div class="flex h-12 flex-shrink-0 items-center justify-between px-4 bg-slate-50/80 border-b border-slate-100">
        <div class="flex items-center gap-2 min-w-0">
          <span class="font-semibold text-slate-800 flex-shrink-0 text-sm">{{ title }}</span>
          <span v-if="selectedName || isNew" class="truncate text-xs text-slate-400">
            / {{ isNew ? '新建技能' : selectedName }}{{ selectedPath && selectedPath !== 'SKILL.md' ? ` / ${selectedPath}` : '' }}
          </span>
        </div>
        <button
          class="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
          type="button"
          @click="handleClose"
        >
          <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="flex min-h-0 flex-1">
        <div class="flex w-48 flex-shrink-0 flex-col border-r border-slate-100">
          <div class="flex-1 overflow-y-auto p-1.5 space-y-1">
            <div v-if="loading" class="px-2.5 py-3 text-xs text-slate-400">加载中...</div>
            <div v-else-if="skills.length === 0" class="px-2.5 py-3 text-xs text-slate-400">暂无技能</div>
            <div
              v-for="skill in skills"
              :key="skill.name"
              class="group relative flex w-full items-center justify-between rounded-lg transition-colors duration-150"
              :class="[
                selectedName === skill.name && !isNew
                  ? 'bg-slate-100 text-slate-900 font-semibold'
                  : 'text-slate-600 hover:bg-slate-50',
              ]"
            >
              <button
                class="flex-1 min-w-0 px-2.5 py-1.5 text-left select-none cursor-pointer outline-none"
                type="button"
                @click="selectSkill(skill.name)"
              >
                <div class="truncate text-xs font-semibold">{{ skill.display_name || skill.name }}</div>
                <div v-if="skill.display_name" class="truncate text-[9px] text-slate-400">{{ skill.name }}</div>
                <div class="truncate text-[10px] text-slate-400 mt-0.5">{{ skill.description || '无描述' }}</div>
              </button>
              <button
                class="mr-1.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-all duration-150"
                title="删除技能"
                type="button"
                @click.stop="remove(skill.name)"
              >
                <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
          <div class="p-1.5 border-t border-slate-100">
            <button
              :class="[
                'flex w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors duration-150',
                isNew
                  ? 'bg-slate-100 text-slate-900 font-semibold'
                  : 'text-slate-600 hover:bg-slate-50',
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

        <div
          v-if="selectedName && !isNew"
          class="flex w-52 flex-shrink-0 flex-col bg-slate-50/50 border-r border-slate-100"
        >
          <div class="flex h-10 items-center justify-between px-2.5 border-b border-slate-100 flex-shrink-0">
            <span class="truncate text-xs font-semibold text-slate-700">{{ selectedName }}</span>
            <div class="flex items-center gap-0.5">
              <button
                class="flex h-6 w-6 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
                title="新建文件"
                type="button"
                @click="addFile('')"
              >
                <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
                </svg>
              </button>
              <button
                class="flex h-6 w-6 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
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
            <div v-if="treeLoading" class="px-2.5 py-3 text-xs text-slate-400">加载文件...</div>
            <template v-else>
              <template v-for="entry in tree" :key="entry.relPath">
                <div
                  v-if="entry.isDir"
                  class="group mt-1 flex h-7 items-center justify-between rounded-lg px-2 text-xs text-slate-500 font-medium"
                >
                  <div class="flex min-w-0 items-center gap-1.5">
                    <svg class="h-3.5 w-3.5 flex-shrink-0 text-slate-400" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7h7l2 2h9v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
                    </svg>
                    <span class="truncate">{{ entry.name }}</span>
                    <span v-if="entry.virtual" class="text-[9px] text-slate-400 font-normal scale-95">virtual</span>
                  </div>
                  <button
                    class="flex h-5 w-5 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
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
                      ? 'bg-slate-100 text-slate-900 font-semibold'
                      : 'text-slate-600 hover:bg-slate-100/40',
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
                    <svg class="h-3.5 w-3.5 flex-shrink-0 text-slate-400" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 3h7l5 5v13H7V3Z" />
                    </svg>
                    <span class="truncate">{{ entry.name }}</span>
                  </button>
                  <button
                    v-if="entry.relPath !== 'SKILL.md'"
                    class="mr-1.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-all duration-150"
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

        <div class="flex min-w-0 flex-1 flex-col">
          <div v-if="!selectedName && !isNew" class="flex flex-1 items-center justify-center text-sm text-[#9ca3af]">
            从左侧选择技能或新建
          </div>

          <template v-else>

            <!-- Scroll Area Wrapper -->
            <div class="relative min-h-0 flex-1">
              <!-- Scroll Area -->
              <div class="h-full overflow-y-auto px-5 pb-12 pt-3">
                <div v-if="fileLoading" class="py-10 text-center text-sm text-[#9ca3af]">加载文件...</div>

                <div v-else class="space-y-6">
                  <template v-if="selectedEditorKind === 'skill'">
                    <template v-if="!rawMode">
                      <div class="mb-3.5">
                        <label class="mb-1 block text-xs font-medium text-slate-500">技能名称</label>
                        <input
                          v-if="isNew"
                          v-model="form.name"
                          class="h-9 w-full rounded-xl border border-slate-200/80 bg-slate-50/50 px-3 text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                          placeholder="my-skill-name（小写字母、数字、连字符）"
                          type="text"
                        />
                        <div v-else class="flex h-9 items-center rounded-xl border border-slate-200 bg-slate-100/50 px-3 text-xs font-medium text-slate-700">
                          {{ selectedName }}
                        </div>
                        <p v-if="nameError" class="mt-1 text-xs text-[#9a3412]">{{ nameError }}</p>
                        <p v-if="parseWarning && !rawMode" class="mt-1 text-xs text-[#92400e]">{{ parseWarning }}</p>
                      </div>

                      <div class="mb-3.5">
                        <div class="mb-1 flex items-baseline justify-between">
                          <label class="block text-xs font-medium text-slate-500">展示名</label>
                          <span
                            :class="[
                              'text-[10px] tabular-nums',
                              (form.display_name ?? '').length > DISPLAY_NAME_MAX ? 'text-[#9a3412]' : 'text-slate-400',
                            ]"
                          >
                            {{ (form.display_name ?? '').length }} / {{ DISPLAY_NAME_MAX }}
                          </span>
                        </div>
                        <input
                          v-model="form.display_name"
                          :maxlength="DISPLAY_NAME_MAX"
                          class="h-9 w-full rounded-xl border border-slate-200/80 bg-slate-50/50 px-3 text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                          placeholder="例如：数学解题助手"
                          type="text"
                        />
                        <p v-if="displayNameError" class="mt-1 text-xs text-[#9a3412]">{{ displayNameError }}</p>
                      </div>

                      <div class="mb-3.5">
                        <div class="mb-1 flex items-baseline justify-between">
                          <label class="block text-xs font-medium text-slate-500">
                            描述 <span class="text-[#9a3412]">*</span>
                          </label>
                          <span
                            :class="[
                              'text-[10px] tabular-nums',
                              form.description.length > DESCRIPTION_MAX ? 'text-[#9a3412]' : 'text-slate-400',
                            ]"
                          >
                            {{ form.description.length }} / {{ DESCRIPTION_MAX }}
                          </span>
                        </div>
                        <textarea
                          ref="descTextarea"
                          v-model="form.description"
                          :maxlength="DESCRIPTION_MAX"
                          class="w-full resize-none overflow-hidden rounded-xl border border-slate-200/80 bg-slate-50/50 p-2.5 text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                          rows="2"
                          @input="autoGrow($event.target as HTMLTextAreaElement)"
                        />
                        <p v-if="descriptionError" class="mt-1 text-xs text-[#9a3412]">{{ descriptionError }}</p>
                      </div>

                      <div class="mb-3.5">
                        <button
                          class="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800"
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
                            <span class="mb-1 block text-xs text-slate-500">license</span>
                            <input
                              v-model="form.license"
                              class="h-9 w-full rounded-xl border border-slate-200/80 bg-slate-50/50 px-3 text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                              placeholder="例如 MIT"
                              type="text"
                            />
                          </label>
                          <label class="block">
                            <div class="mb-1 flex items-baseline justify-between">
                              <span class="block text-xs text-slate-500">compatibility</span>
                              <span
                                :class="[
                                  'text-[10px] tabular-nums',
                                  (form.compatibility ?? '').length > COMPATIBILITY_MAX ? 'text-[#9a3412]' : 'text-slate-400',
                                ]"
                              >
                                {{ (form.compatibility ?? '').length }} / {{ COMPATIBILITY_MAX }}
                              </span>
                            </div>
                            <input
                              v-model="form.compatibility"
                              :maxlength="COMPATIBILITY_MAX"
                              class="h-9 w-full rounded-xl border border-slate-200/80 bg-slate-50/50 px-3 text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                              placeholder="兼容性说明"
                              type="text"
                            />
                            <p v-if="compatibilityError" class="mt-1 text-xs text-[#9a3412]">{{ compatibilityError }}</p>
                          </label>
                        </div>
                      </div>

                      <div class="mb-4">
                        <div class="mb-1 flex items-baseline justify-between">
                          <label class="block text-xs font-medium text-slate-500">技能内容（Markdown）</label>
                          <span class="text-[10px] tabular-nums text-slate-400">
                            {{ bodyCharCount.toLocaleString() }} 字符 · {{ bodyLineCount }} 行
                          </span>
                        </div>
                        <textarea
                          ref="bodyTextarea"
                          v-model="form.body"
                          class="w-full resize-none overflow-hidden rounded-xl border border-slate-200/80 bg-slate-50/50 p-3 font-mono text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                          style="min-height: 250px"
                          spellcheck="false"
                          @input="autoGrow($event.target as HTMLTextAreaElement)"
                        />
                        <p class="mt-1 text-[10px] text-slate-400">前端会自动生成合法的 frontmatter（name/description 等），你无需手动写 `---` 分隔块。</p>
                      </div>
                    </template>

                    <template v-else>
                      <div class="mb-2 flex items-center justify-between">
                        <span class="text-xs font-medium text-slate-500">原始 SKILL.md 编辑</span>
                        <button
                          class="text-xs font-semibold text-slate-800 hover:underline"
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
                        class="w-full resize-none overflow-hidden rounded-xl border border-slate-200/80 bg-slate-50/50 p-3 font-mono text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                        style="min-height: 360px"
                        spellcheck="false"
                        @input="autoGrow($event.target as HTMLTextAreaElement)"
                      />
                    </template>
                  </template>

                  <template v-else>
                    <div v-if="isImageFile" class="flex flex-col items-center justify-center p-8 rounded-2xl bg-slate-50/50 border border-slate-100" style="min-height: 420px">
                      <span class="text-3xl mb-2">🖼️</span>
                      <p class="text-xs text-slate-600 font-semibold">图片文件仅支持管理，无法直接编辑内容。</p>
                      <p class="text-[10px] text-slate-400 mt-1">{{ selectedPath }}</p>
                    </div>
                    <template v-else>
                      <div class="mb-1 flex items-baseline justify-between">
                        <label class="block text-xs font-medium text-slate-500">文本内容</label>
                        <span class="text-[10px] tabular-nums text-slate-400">
                          {{ plainCharCount.toLocaleString() }} 字符 · {{ plainLineCount }} 行
                        </span>
                      </div>
                      <textarea
                        ref="plainTextarea"
                        v-model="plainContent"
                        class="w-full resize-none overflow-hidden rounded-xl border border-slate-200/80 bg-slate-50/50 p-3 font-mono text-xs outline-none transition duration-150 focus:bg-white focus:border-slate-400 focus:ring-2 focus:ring-slate-900/5"
                        style="min-height: 420px"
                        spellcheck="false"
                        @input="autoGrow($event.target as HTMLTextAreaElement)"
                      />
                    </template>
                  </template>

                  <!-- Actions inside the card -->
                  <div v-if="canPublish || errorMsg || publishMsg" class="mt-4 pt-3.5 border-t border-slate-100 flex-shrink-0 bg-white">
                    <p v-if="errorMsg" class="mb-3 rounded-xl bg-rose-50/60 border border-rose-200/50 px-3 py-2 text-xs text-rose-800">
                      {{ errorMsg }}
                    </p>
                    <p v-if="publishMsg" class="mb-3 rounded-xl bg-emerald-50/60 border border-emerald-200/50 px-3 py-2 text-xs text-emerald-800">
                      {{ publishMsg }}
                    </p>
                    <div v-if="canPublish" class="flex items-center justify-end">
                      <div class="flex items-center gap-2">
                        <button
                          class="rounded-xl bg-slate-100 px-3.5 py-1.5 text-xs text-slate-700 font-semibold transition-all duration-200 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
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
              </div>

              <!-- Floating Save Button -->
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
          </template>
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

