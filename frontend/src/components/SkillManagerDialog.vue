<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted } from 'vue'
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
const selectedFileLabel = computed(() => selectedPath.value ?? (isNew.value ? 'SKILL.md' : ''))
const canDeleteSelectedFile = computed(() =>
  !!selectedName.value
  && !!selectedPath.value
  && selectedPath.value !== 'SKILL.md'
  && currentEntry.value?.isDir !== true,
)
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

async function remove(): Promise<void> {
  if (!selectedName.value) return
  if (!confirm(`确定要删除技能 "${selectedName.value}" 吗？此操作不可撤销。`)) return
  deleting.value = true
  errorMsg.value = ''
  publishMsg.value = ''
  try {
    await deleteSkill(props.space, selectedName.value)
    selectedName.value = null
    selectedPath.value = null
    tree.value = []
    resetEditor()
    await loadSkills()
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    deleting.value = false
  }
}

async function removeSelectedFile(): Promise<void> {
  if (!selectedName.value || !selectedPath.value || selectedPath.value === 'SKILL.md') return
  if (!confirm(`确定要删除文件 "${selectedPath.value}" 吗？此操作不可撤销。`)) return
  deletingFile.value = true
  errorMsg.value = ''
  publishMsg.value = ''
  try {
    await deleteSkillFile(props.space, selectedName.value, selectedPath.value)
    await loadTree(selectedName.value)
    await openFile('SKILL.md', false)
  } catch (e) {
    errorMsg.value = getErrorMessage(e)
  } finally {
    deletingFile.value = false
  }
}

function askTargetFolder(defaultFolder: '' | SkillResourceDir = ''): '' | SkillResourceDir | null {
  const raw = prompt('目标文件夹：留空表示技能根目录，或输入 references / assets', defaultFolder)
  if (raw === null) return null
  const value = raw.trim()
  if (value === '') return ''
  if ((SKILL_RESOURCE_DIRS as readonly string[]).includes(value)) return value as SkillResourceDir
  errorMsg.value = '只能使用 references 或 assets 文件夹。'
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
  const raw = prompt('文件夹名（只能是 references 或 assets）')
  if (raw === null) return
  const name = raw.trim()
  if (!(SKILL_RESOURCE_DIRS as readonly string[]).includes(name)) {
    errorMsg.value = '只能新建 references 或 assets 文件夹。'
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
  <div class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40" @click.self="handleClose">
    <div class="flex h-[680px] w-[1080px] max-w-[96vw] flex-col rounded-xl bg-white shadow-xl overflow-hidden">
      <div class="flex h-14 flex-shrink-0 items-center justify-between px-5">
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
        <div class="flex w-52 flex-shrink-0 flex-col">
          <div class="flex-1 overflow-y-auto p-2">
            <div v-if="loading" class="px-3 py-4 text-sm text-[#9ca3af]">加载中...</div>
            <div v-else-if="skills.length === 0" class="px-3 py-4 text-sm text-[#9ca3af]">暂无技能</div>
            <button
              v-for="skill in skills"
              :key="skill.name"
              :class="[
                'w-full rounded-md px-3 py-2 text-left transition-colors',
                selectedName === skill.name && !isNew
                  ? 'bg-[#e5e7eb] text-[#1f2937] font-medium'
                  : 'text-[#374151] hover:bg-[#f3f4f6]',
              ]"
              type="button"
              @click="selectSkill(skill.name)"
            >
              <div class="truncate text-sm font-medium">{{ skill.display_name || skill.name }}</div>
              <div v-if="skill.display_name" class="truncate text-[10px] text-[#9ca3af]">{{ skill.name }}</div>
              <div class="truncate text-xs text-[#9ca3af]">{{ skill.description || '无描述' }}</div>
            </button>
          </div>
          <div class="p-2">
            <button
              :class="[
                'flex w-full items-center gap-1.5 rounded-md px-3 py-2 text-sm transition-colors',
                isNew ? 'bg-[#e5e7eb] text-[#1f2937] font-medium' : 'text-[#374151] hover:bg-[#f3f4f6]',
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
          class="flex w-60 flex-shrink-0 flex-col bg-[#fafafa]"
        >
          <div class="flex h-12 items-center justify-between px-3">
            <span class="truncate text-sm font-medium text-[#374151]">{{ selectedName }}</span>
            <div class="flex items-center gap-1">
              <button
                class="flex h-7 w-7 items-center justify-center rounded-md text-[#6b7280] hover:bg-[#e5e7eb] hover:text-[#1f2937]"
                title="新建文件"
                type="button"
                @click="addFile('')"
              >
                <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
                </svg>
              </button>
              <button
                class="flex h-7 w-7 items-center justify-center rounded-md text-[#6b7280] hover:bg-[#e5e7eb] hover:text-[#1f2937]"
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
          <div class="min-h-0 flex-1 overflow-y-auto p-2">
            <div v-if="treeLoading" class="px-3 py-4 text-sm text-[#9ca3af]">加载文件...</div>
            <template v-else>
              <template v-for="entry in tree" :key="entry.relPath">
                <div
                  v-if="entry.isDir"
                  class="group mt-1 flex h-8 items-center justify-between rounded-md px-2 text-sm text-[#6b7280]"
                >
                  <div class="flex min-w-0 items-center gap-1.5">
                    <svg class="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7h7l2 2h9v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
                    </svg>
                    <span class="truncate">{{ entry.name }}</span>
                    <span v-if="entry.virtual" class="text-[10px] text-[#9ca3af]">virtual</span>
                  </div>
                  <button
                    class="flex h-6 w-6 items-center justify-center rounded text-[#9ca3af] hover:bg-[#e5e7eb] hover:text-[#1f2937]"
                    :title="`在 ${entry.name}/ 中新建文件`"
                    type="button"
                    @click.stop="addFile(entry.name as SkillResourceDir)"
                  >
                    <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M12 5v14m7-7H5" />
                    </svg>
                  </button>
                </div>
                <button
                  v-else
                  :class="[
                    'flex h-8 w-full items-center gap-1.5 rounded-md px-2 text-left text-sm transition-colors',
                    entry.parent ? 'pl-7' : '',
                    selectedPath === entry.relPath
                      ? 'bg-[#e5e7eb] text-[#1f2937] font-medium'
                      : 'text-[#374151] hover:bg-white',
                  ]"
                  type="button"
                  @click="openFile(entry.relPath)"
                >
                  <svg class="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 3h7l5 5v13H7V3Z" />
                  </svg>
                  <span class="truncate">{{ entry.name }}</span>
                </button>
              </template>
            </template>
          </div>
        </div>

        <div class="flex min-w-0 flex-1 flex-col">
          <div v-if="!selectedName && !isNew" class="flex flex-1 items-center justify-center text-sm text-[#9ca3af]">
            从左侧选择技能或新建
          </div>

          <template v-else>
            <div class="flex h-12 flex-shrink-0 items-center justify-between px-5">
              <div class="min-w-0">
                <div class="truncate text-sm font-medium text-[#1f2937]">{{ selectedFileLabel }}</div>
                <div v-if="selectedEditorKind && selectedEditorKind !== 'skill'" class="text-xs text-[#9ca3af]">
                  {{ selectedEditorKind }}
                </div>
              </div>
            </div>

            <!-- Scroll Area Wrapper with top and bottom gradient overlays -->
            <div class="relative min-h-0 flex-1">
              <!-- Top fade gradient overlay -->
              <div class="pointer-events-none absolute left-0 right-0 top-0 h-6 bg-gradient-to-b from-white via-white/70 to-transparent z-10" />
              <!-- Bottom fade gradient overlay -->
              <div class="pointer-events-none absolute left-0 right-0 bottom-0 h-6 bg-gradient-to-t from-white via-white/70 to-transparent z-10" />

              <!-- Scroll Area -->
              <div class="h-full overflow-y-auto px-5 pb-5 pt-3">
                <div v-if="fileLoading" class="py-10 text-center text-sm text-[#9ca3af]">加载文件...</div>

                <div v-else class="rounded-2xl border border-gray-200 bg-[#f3f4f6] p-6 shadow-md">
                  <template v-if="selectedEditorKind === 'skill'">
                    <template v-if="!rawMode">
                      <div class="mb-4">
                        <label class="mb-1 block text-xs font-medium text-[#6b7280]">技能名称</label>
                        <input
                          v-if="isNew"
                          v-model="form.name"
                          class="h-9 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                          placeholder="my-skill-name（小写字母、数字、连字符）"
                          type="text"
                        />
                        <div v-else class="flex h-9 items-center rounded-md bg-[#e5e7eb] px-3 text-sm text-[#374151]">
                          {{ selectedName }}
                        </div>
                        <p v-if="nameError" class="mt-1 text-xs text-[#9a3412]">{{ nameError }}</p>
                        <p v-if="parseWarning && !rawMode" class="mt-1 text-xs text-[#92400e]">{{ parseWarning }}</p>
                      </div>

                      <div class="mb-4">
                        <div class="mb-1 flex items-baseline justify-between">
                          <label class="block text-xs font-medium text-[#6b7280]">展示名</label>
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
                          class="h-9 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                          placeholder="例如：数学解题助手"
                          type="text"
                        />
                        <p v-if="displayNameError" class="mt-1 text-xs text-[#9a3412]">{{ displayNameError }}</p>
                      </div>

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
                          class="w-full resize-y rounded-md border border-[#d1d5db] bg-white p-2.5 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                          rows="2"
                        />
                        <p v-if="descriptionError" class="mt-1 text-xs text-[#9a3412]">{{ descriptionError }}</p>
                      </div>

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
                              class="h-9 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
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
                              class="h-9 w-full rounded-md border border-[#d1d5db] bg-white px-3 text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                              placeholder="兼容性说明"
                              type="text"
                            />
                            <p v-if="compatibilityError" class="mt-1 text-xs text-[#9a3412]">{{ compatibilityError }}</p>
                          </label>
                        </div>
                      </div>

                      <div class="mb-5">
                        <div class="mb-1 flex items-baseline justify-between">
                          <label class="block text-xs font-medium text-[#6b7280]">技能内容（Markdown）</label>
                          <span class="text-[10px] tabular-nums text-[#9ca3af]">
                            {{ bodyCharCount.toLocaleString() }} 字符 · {{ bodyLineCount }} 行
                          </span>
                        </div>
                        <textarea
                          v-model="form.body"
                          class="w-full resize-y rounded-md border border-[#d1d5db] bg-white p-3 font-mono text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                          style="min-height: 250px"
                          spellcheck="false"
                        />
                        <p class="mt-1 text-[10px] text-[#9ca3af]">前端会自动生成合法的 frontmatter（name/description 等），你无需手动写 `---` 分隔块。</p>
                      </div>
                    </template>

                    <template v-else>
                      <div class="mb-3 flex items-center justify-between">
                        <span class="text-xs font-medium text-[#6b7280]">原始 SKILL.md 编辑</span>
                        <button
                          class="text-xs text-[#1f2937] hover:underline"
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
                        class="w-full resize-y rounded-md border border-[#d1d5db] bg-white p-3 font-mono text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                        style="min-height: 360px"
                        spellcheck="false"
                      />
                    </template>
                  </template>

                  <template v-else>
                    <div v-if="isImageFile" class="flex flex-col items-center justify-center p-8 border border-[#e5e7eb] rounded-md bg-[#f9fafb]" style="min-height: 420px">
                      <span class="text-3xl mb-2">🖼️</span>
                      <p class="text-sm text-[#4b5563] font-medium">图片文件仅支持管理，无法直接编辑内容。</p>
                      <p class="text-xs text-[#9ca3af] mt-1">{{ selectedPath }}</p>
                    </div>
                    <template v-else>
                      <div class="mb-1 flex items-baseline justify-between">
                        <label class="block text-xs font-medium text-[#6b7280]">文本内容</label>
                        <span class="text-[10px] tabular-nums text-[#9ca3af]">
                          {{ plainCharCount.toLocaleString() }} 字符 · {{ plainLineCount }} 行
                        </span>
                      </div>
                      <textarea
                        v-model="plainContent"
                        class="w-full resize-y rounded-md border border-[#d1d5db] bg-white p-3 font-mono text-sm outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                        style="min-height: 420px"
                        spellcheck="false"
                      />
                    </template>
                  </template>

                  <!-- Actions inside the card -->
                  <div class="mt-4 border-t border-gray-200/50 pt-3.5">
                    <p v-if="errorMsg" class="mb-3 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-xs text-[#9a3412]">
                      {{ errorMsg }}
                    </p>
                    <p v-if="publishMsg" class="mb-3 rounded-md border border-[#bbf7d0] bg-[#f0fdf4] px-3 py-2 text-xs text-[#166534]">
                      {{ publishMsg }}
                    </p>
                    <div class="flex items-center justify-between">
                      <button
                        v-if="!isNew && selectedName && selectedPath === 'SKILL.md'"
                        class="rounded-md px-3 py-1.5 text-sm text-[#9a3412] transition hover:bg-[#fff7ed] disabled:opacity-50"
                        :disabled="deleting"
                        type="button"
                        @click="remove"
                      >
                        {{ deleting ? '删除中...' : '删除技能' }}
                      </button>
                      <button
                        v-else-if="canDeleteSelectedFile"
                        class="rounded-md px-3 py-1.5 text-sm text-[#9a3412] transition hover:bg-[#fff7ed] disabled:opacity-50"
                        :disabled="deletingFile"
                        type="button"
                        @click="removeSelectedFile"
                      >
                        {{ deletingFile ? '删除中...' : '删除文件' }}
                      </button>
                      <div v-else />
                      <div class="flex items-center gap-2">
                        <button
                          v-if="canPublish"
                          class="rounded-md border border-[#1f2937] px-3 py-1.5 text-sm text-[#1f2937] transition hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
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
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>
