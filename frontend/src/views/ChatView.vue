<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import MessageContent from '../components/MessageContent.vue'
import SkillPicker from '../components/SkillPicker.vue'
import SkillChips from '../components/SkillChips.vue'
import EditPromptDialog from '../components/EditPromptDialog.vue'
import MediaPreviewDialog from '../components/MediaPreviewDialog.vue'
import WindowManager from '../components/WindowManager.vue'
import SkillEditorPanel from '../components/SkillEditorPanel.vue'
import {
  deleteTurn,
  getMessageBlocks,
  getErrorMessage,
  listMessageVersions,
  listMessageBlockIndex,
  listSessions,
  regenerateChatMessage,
  sendChatMessage,
  stopChatGeneration,
  syncMessageBlockDelta,
  switchMessageVersion,
  type DisplayMessageBlock,
  type DisplayMessage,
  type MessageBlockIndexItem,
  type MessageVersionItem,
  type ProjectItem,
  type SessionItem,
  uploadAttachment,
  deleteAttachment,
  listAttachments,
  getAttachmentBlobUrl,
  readFile,
  type AttachmentItem,
} from '../api'
import { type SkillMeta } from '../skills'
import { useAuth } from '../composables/useAuth'
import { useProjects } from '../composables/useProjects'
import { useProjectSkills } from '../composables/useProjectSkills'
import { useUserSkills } from '../composables/useUserSkills'
import { usePreferences } from '../composables/usePreferences'
import { useChatSkillSidebar } from '../composables/useChatSkillSidebar'
import { confirmDanger } from '../composables/useConfirmDialog'
import {
  CHAT_ATTACHMENT_MAX_BYTES,
  CHAT_COMPOSER_MAX_HEIGHT,
  CHAT_COPY_RESET_MS,
  CHAT_DRAWER_ENTER_MAX_HEIGHT_MS,
  CHAT_DRAWER_ENTER_OPACITY_MS,
  CHAT_DRAWER_LEAVE_MAX_HEIGHT_MS,
  CHAT_DRAWER_LEAVE_OPACITY_MS,
  CHAT_SCROLL_BOTTOM_THRESHOLD,
  PLACEHOLDERS,
} from '../config'

const route = useRoute()
const router = useRouter()
const { projects, loadProjects } = useProjects()
const { preparing } = useAuth()
const { editingSkill, closeEditor } = useChatSkillSidebar()

import { useNotification } from '../composables/useNotification'
const errorMessage = ref('')
const { showError } = useNotification()

watch(errorMessage, (newVal) => {
  if (newVal) {
    showError(newVal)
    // Clear local error message immediately so that it is only displayed in the global toast
    errorMessage.value = ''
  }
})

const pid = computed(() => route.params.pid as string)
const sid = computed(() => route.params.sid as string)
const currentProject = computed<ProjectItem | null>(
  () => projects.value.find((p) => p.pid === pid.value) ?? null,
)
const currentSession = ref<SessionItem | null>(null)

// ── 聊天状态 ─────────────────────────────────────────────────────────────────
const streaming = ref(false)
const toolStatus = ref('')
const draft = ref('')
// 消息缓存与渲染
const blockIndex = ref<MessageBlockIndexItem[]>([])
const blockContentCache = ref<Record<string, DisplayMessage[]>>({})
const messageRevision = ref('')
const pendingBlockContentLoads = new Set<string>()
const chatContainer = ref<HTMLElement | null>(null)
const currentAbort = ref<AbortController | null>(null)
const stickToBottom = ref(true)
const composerTextarea = ref<HTMLTextAreaElement | null>(null)
const composerFooter = ref<HTMLElement | null>(null)
const composerHeight = ref(128)
let footerResizeObserver: ResizeObserver | null = null
const copiedId = ref<string | null>(null)
let copyResetTimer: number | null = null
// 当前正在生成的那条 user 输入（不含 skill 前缀），用于 stop 后回填到输入框
const inflightUserPrompt = ref<string>('')
const sessionAttachments = ref<AttachmentItem[]>([])
const attachmentUrls = ref<Record<string, string>>({})

const CHAT_CACHE_SCHEMA = 3
const CHAT_CACHE_PREFIX = 'chat_cache_'
const BLOCK_GAP_PX = 20
const CHAT_TOP_PADDING_PX = 64
const VIRTUAL_BLOCK_LIMIT = 10
const VIRTUAL_BLOCK_OVERSCAN_PX = 720

interface ChatCachePayload {
  schema?: number
  revision?: string
  blockIndex?: MessageBlockIndexItem[]
  blockContentCache?: Record<string, DisplayMessage[]>
  attachments: AttachmentItem[]
  blockHeights?: Record<string, number>
  versionsByAnchor?: Record<string, MessageVersionItem[]>
  timestamp: number
}

interface MessageBlock {
  id: string
  index: MessageBlockIndexItem
  messages: DisplayMessage[]
}

const blockHeights = ref<Record<string, number>>({})
const virtualStart = ref(0)
const virtualEnd = ref(0)
const virtualBlockElements = new Map<string, HTMLElement>()
let virtualResizeObserver: ResizeObserver | null = null
let virtualScrollRaf: number | null = null
let saveHeightCacheTimer: number | null = null

// ── 版本（重放）状态 ─────────────────────────────────────────────────────────
// 每个 anchor 的全部版本快照，用于角标显示与版本切换
const versionsByAnchor = ref<Record<string, MessageVersionItem[]>>({})
// 用户当前在该 anchor 下"看到"的是第几个版本（1-based）。
// 由于后端用 swap 表示"切换"——切换后 version=0 仍然是活跃——这里用客户端指针
// 来维持用户的视觉位置。loadMessages 时若 anchor 已知则保留位置，未知则置 1。
const displayedPosByAnchor = ref<Record<string, number>>({})

const messageBlocks = computed<MessageBlock[]>(() => (
  blockIndex.value.map((index) => ({
    id: index.block_id,
    index,
    messages: blockContentCache.value[index.block_id] ?? [],
  }))
))

function blockContentHeight(block: MessageBlock): number {
  return blockHeights.value[block.id] ?? block.index.estimated_height
}

function blockUnitHeight(block: MessageBlock, index: number, total: number): number {
  return blockContentHeight(block) + (index < total - 1 ? BLOCK_GAP_PX : 0)
}

const blockMetrics = computed(() => {
  const blocks = messageBlocks.value
  const offsets: number[] = []
  let total = 0
  for (let i = 0; i < blocks.length; i++) {
    offsets.push(total)
    total += blockUnitHeight(blocks[i], i, blocks.length)
  }
  return { offsets, total }
})

const virtualBlocks = computed<MessageBlock[]>(() => (
  messageBlocks.value.slice(virtualStart.value, virtualEnd.value)
))

const visibleMessages = computed<DisplayMessage[]>(() => (
  virtualBlocks.value.flatMap((block) => block.messages)
))

const topSpacerHeight = computed(() => {
  if (messageBlocks.value.length === 0) return 0
  return blockMetrics.value.offsets[virtualStart.value] ?? 0
})

const bottomSpacerHeight = computed(() => {
  if (messageBlocks.value.length === 0) return 0
  const end = Math.min(virtualEnd.value, messageBlocks.value.length)
  if (end >= messageBlocks.value.length) return 0
  return Math.max(0, blockMetrics.value.total - (blockMetrics.value.offsets[end] ?? blockMetrics.value.total))
})

function chatCacheKey(sessionId: string): string {
  return `${CHAT_CACHE_PREFIX}${sessionId}`
}

function readChatCache(sessionId: string): ChatCachePayload | null {
  try {
    const raw = localStorage.getItem(chatCacheKey(sessionId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as ChatCachePayload
    if (!parsed || !Array.isArray(parsed.blockIndex) || !Array.isArray(parsed.attachments)) {
      return null
    }
    return parsed
  } catch (error) {
    console.warn('Failed to restore chat cache:', error)
    return null
  }
}

function writeChatCache(sessionId: string): void {
  try {
    const payload: ChatCachePayload = {
      schema: CHAT_CACHE_SCHEMA,
      revision: messageRevision.value,
      blockIndex: blockIndex.value,
      blockContentCache: blockContentCache.value,
      attachments: sessionAttachments.value,
      blockHeights: blockHeights.value,
      versionsByAnchor: versionsByAnchor.value,
      timestamp: Date.now(),
    }
    localStorage.setItem(chatCacheKey(sessionId), JSON.stringify(payload))
  } catch (error) {
    console.warn('Failed to save chat cache:', error)
  }
}

function applyChatCache(sessionId: string): boolean {
  const cached = readChatCache(sessionId)
  if (!cached) return false

  messageRevision.value = cached.revision ?? ''
  blockIndex.value = cached.blockIndex ?? []
  blockContentCache.value = cached.blockContentCache ?? {}
  sessionAttachments.value = cached.attachments
  blockHeights.value = cached.blockHeights ?? {}
  versionsByAnchor.value = cached.versionsByAnchor ?? versionsByAnchor.value
  setVirtualWindowToBottom()
  void ensureVisibleBlockContents()
  void refreshVisibleMessageAssets()
  scrollToBottom(true)
  return true
}

function scheduleChatCacheSave(): void {
  const sessionId = currentSession.value?.sid
  if (!sessionId) return
  if (saveHeightCacheTimer) window.clearTimeout(saveHeightCacheTimer)
  saveHeightCacheTimer = window.setTimeout(() => {
    saveHeightCacheTimer = null
    writeChatCache(sessionId)
  }, 250)
}

function resetMessageViewState(): void {
  blockIndex.value = []
  blockContentCache.value = {}
  messageRevision.value = ''
  pendingBlockContentLoads.clear()
  sessionAttachments.value = []
  blockHeights.value = {}
  versionsByAnchor.value = {}
  displayedPosByAnchor.value = {}
  virtualStart.value = 0
  virtualEnd.value = 0
  clearAttachmentUrls()
}

function setVirtualWindowToBottom(): void {
  const total = messageBlocks.value.length
  if (total === 0) {
    virtualStart.value = 0
    virtualEnd.value = 0
    return
  }
  virtualEnd.value = total
  virtualStart.value = Math.max(0, total - VIRTUAL_BLOCK_LIMIT)
}

function updateVirtualWindowFromScroll(): void {
  const blocks = messageBlocks.value
  const container = chatContainer.value
  if (!container || blocks.length === 0) {
    virtualStart.value = 0
    virtualEnd.value = blocks.length
    return
  }

  const { offsets, total } = blockMetrics.value
  const viewportTop = Math.max(0, container.scrollTop - CHAT_TOP_PADDING_PX)
  const viewportBottom = viewportTop + container.clientHeight
  const targetTop = Math.max(0, viewportTop - VIRTUAL_BLOCK_OVERSCAN_PX)
  let start = 0

  for (let i = 0; i < blocks.length; i++) {
    const blockBottom = offsets[i] + blockUnitHeight(blocks[i], i, blocks.length)
    if (blockBottom >= targetTop) {
      start = Math.max(0, i - 1)
      break
    }
  }

  let end = Math.min(blocks.length, start + VIRTUAL_BLOCK_LIMIT)
  const targetBottom = Math.min(total, viewportBottom + VIRTUAL_BLOCK_OVERSCAN_PX)
  while (
    end < blocks.length &&
    (offsets[end] ?? total) < targetBottom &&
    end - start < VIRTUAL_BLOCK_LIMIT + 4
  ) {
    end += 1
  }

  if (end >= blocks.length) {
    end = blocks.length
    start = Math.max(0, end - VIRTUAL_BLOCK_LIMIT)
  }

  virtualStart.value = start
  virtualEnd.value = end
}

function scheduleVirtualWindowUpdate(): void {
  if (virtualScrollRaf !== null) return
  virtualScrollRaf = window.requestAnimationFrame(() => {
    virtualScrollRaf = null
    updateVirtualWindowFromScroll()
  })
}

function ensureVirtualResizeObserver(): ResizeObserver {
  if (!virtualResizeObserver) {
    virtualResizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const target = entry.target as HTMLElement
        const blockId = target.dataset.blockId
        if (blockId) measureVirtualBlock(blockId, target)
      }
    })
  }
  return virtualResizeObserver
}

function setVirtualBlockElement(blockId: string, el: Element | ComponentPublicInstance | null): void {
  const previous = virtualBlockElements.get(blockId)
  if (previous && previous !== el) {
    virtualResizeObserver?.unobserve(previous)
    virtualBlockElements.delete(blockId)
  }

  if (!(el instanceof HTMLElement)) return
  virtualBlockElements.set(blockId, el)
  el.dataset.blockId = blockId
  ensureVirtualResizeObserver().observe(el)
  measureVirtualBlock(blockId, el)
}

function measureVirtualBlock(blockId: string, el: HTMLElement): void {
  const measured = Math.ceil(el.getBoundingClientRect().height)
  if (measured <= 0) return
  const previous = blockHeights.value[blockId]
  if (previous && Math.abs(previous - measured) <= 1) return

  blockHeights.value = { ...blockHeights.value, [blockId]: measured }
  scheduleVirtualWindowUpdate()
  scheduleChatCacheSave()
  if (stickToBottom.value) {
    scrollToBottom()
  }
}

// 编辑 PROMPT 弹窗
const editDialogOpen = ref(false)
const editDialogAnchor = ref<string | null>(null)
const editDialogInitial = ref('')

// 媒体多开预览（最多 8 个）
interface PreviewItem {
  id: string
  type: 'image' | 'mermaid' | 'math' | 'table'
  source: string
  index: number
  windowX?: number
  windowY?: number
  windowWidth?: number
  windowHeight?: number
  dockLeft?: boolean
  dockRight?: boolean
  dockTop?: boolean
  dockBottom?: boolean
  relX?: number
  relY?: number
  minimized?: boolean
}
const activePreviews = ref<PreviewItem[]>([])
const messagesLoaded = ref(false)
const highlightedPreviewId = ref<string | null>(null)
let highlightTimeout: number | null = null

function closePreview(id: string): void {
  activePreviews.value = activePreviews.value.filter((p) => p.id !== id)
}

function focusPreview(id: string): void {
  const existingIdx = activePreviews.value.findIndex((p) => p.id === id)
  if (existingIdx !== -1) {
    if (activePreviews.value[existingIdx].minimized) {
      activePreviews.value[existingIdx].minimized = false
    }

    if (existingIdx !== activePreviews.value.length - 1) {
      const [item] = activePreviews.value.splice(existingIdx, 1)
      activePreviews.value.push(item)
    }

    // Trigger highlight for 1 second
    highlightedPreviewId.value = id
    if (highlightTimeout) {
      clearTimeout(highlightTimeout)
    }
    highlightTimeout = window.setTimeout(() => {
      highlightedPreviewId.value = null
      highlightTimeout = null
    }, 1000)
  }
}

function toggleMinimizePreview(id: string): void {
  const preview = activePreviews.value.find((p) => p.id === id)
  if (preview) {
    preview.minimized = !preview.minimized
  }
}

function updatePreviewRect(id: string, rect: {
  x: number
  y: number
  width: number
  height: number
  dockLeft?: boolean
  dockRight?: boolean
  dockTop?: boolean
  dockBottom?: boolean
  relX?: number
  relY?: number
}): void {
  const preview = activePreviews.value.find((p) => p.id === id)
  if (preview) {
    preview.windowX = rect.x
    preview.windowY = rect.y
    preview.windowWidth = rect.width
    preview.windowHeight = rect.height
    preview.dockLeft = rect.dockLeft
    preview.dockRight = rect.dockRight
    preview.dockTop = rect.dockTop
    preview.dockBottom = rect.dockBottom
    preview.relX = rect.relX
    preview.relY = rect.relY
  }
}

// Watch activePreviews deeply to persist to localStorage for the current session
watch(
  () => activePreviews.value,
  () => {
    const sidVal = currentSession.value?.sid
    if (sidVal) {
      localStorage.setItem(`preview_windows_${sidVal}`, JSON.stringify(activePreviews.value))
    }
  },
  { deep: true }
)

async function openImagePreview(url: string): Promise<void> {
  if (!messagesLoaded.value) return
  let type: 'image' | 'mermaid' = 'image'
  let source = url

  if (
    url &&
    !url.startsWith('blob:') &&
    !url.startsWith('data:') &&
    !url.startsWith('http:') &&
    !url.startsWith('https:') &&
    url.toLowerCase().endsWith('.mermaid')
  ) {
    // 相对路径，视为项目文件
    try {
      // 读取 mermaid 文本内容
      const fileData = await readFile({ kind: 'project', pid: pid.value }, url)
      type = 'mermaid'
      source = fileData.content
    } catch (err) {
      console.error('Failed to load project file for preview:', err)
      source = url
    }
  } else {
    source = url
  }

  // Check if already open
  const existingIdx = activePreviews.value.findIndex((p) => p.source === source)
  if (existingIdx !== -1) {
    focusPreview(activePreviews.value[existingIdx].id)
    return
  }

  if (activePreviews.value.length >= 8) {
    showError('最多只能同时打开 8 个预览窗口')
    return
  }

  // Find lowest available index (1 to 8)
  const usedIndices = activePreviews.value.map((p) => p.index)
  let index = 1
  while (usedIndices.includes(index)) {
    index++
  }

  const id = Date.now().toString() + Math.random().toString(36).substring(2, 9)
  activePreviews.value.push({ id, type, source, index })
}

function openMermaidPreview(source: string): void {
  if (!messagesLoaded.value) return
  // Check if already open
  const existingIdx = activePreviews.value.findIndex((p) => p.source === source)
  if (existingIdx !== -1) {
    focusPreview(activePreviews.value[existingIdx].id)
    return
  }

  if (activePreviews.value.length >= 8) {
    showError('最多只能同时打开 8 个预览窗口')
    return
  }

  // Find lowest available index (1 to 8)
  const usedIndices = activePreviews.value.map((p) => p.index)
  let index = 1
  while (usedIndices.includes(index)) {
    index++
  }

  const id = Date.now().toString() + Math.random().toString(36).substring(2, 9)
  activePreviews.value.push({ id, type: 'mermaid', source, index })
}

function openMathPreview(source: string): void {
  if (!messagesLoaded.value) return
  const existingIdx = activePreviews.value.findIndex((p) => p.type === 'math' && p.source === source)
  if (existingIdx !== -1) {
    focusPreview(activePreviews.value[existingIdx].id)
    return
  }

  if (activePreviews.value.length >= 8) {
    showError('最多只能同时打开 8 个预览窗口')
    return
  }

  const usedIndices = activePreviews.value.map((p) => p.index)
  let index = 1
  while (usedIndices.includes(index)) {
    index++
  }

  const id = Date.now().toString() + Math.random().toString(36).substring(2, 9)
  activePreviews.value.push({ id, type: 'math', source, index })
}

function openTablePreview(source: string): void {
  if (!messagesLoaded.value) return
  const existingIdx = activePreviews.value.findIndex((p) => p.type === 'table' && p.source === source)
  if (existingIdx !== -1) {
    focusPreview(activePreviews.value[existingIdx].id)
    return
  }

  if (activePreviews.value.length >= 8) {
    showError('最多只能同时打开 8 个预览窗口')
    return
  }

  const usedIndices = activePreviews.value.map((p) => p.index)
  let index = 1
  while (usedIndices.includes(index)) {
    index++
  }

  const id = Date.now().toString() + Math.random().toString(36).substring(2, 9)
  activePreviews.value.push({ id, type: 'table', source, index })
}


const isChatReady = computed(
  () => Boolean(currentProject.value && currentSession.value && !preparing.value),
)
const canSend = computed(() => Boolean(draft.value.trim() && isChatReady.value && !streaming.value))

// ── Skill 状态 ──────────────────────────────────────────────────────────────
// projectSkills 与 userSkills 由共享 composable 提供，pid 变化或 App.vue 的对话框刷新时自动更新
const pidOrNull = computed(() => pid.value || null)
const { skills: projectSkills } = useProjectSkills(pidOrNull)
const { skills: userSkills, load: loadUserSkills } = useUserSkills()

interface ChatSkillMeta extends SkillMeta {
  rawName: string
  kind: 'user' | 'project'
}

const allSkills = computed<ChatSkillMeta[]>(() => {
  const pList = projectSkills.value.map((s) => ({
    ...s,
    name: `project-${s.name}`,
    rawName: s.name,
    display_name: `${s.display_name || s.name} [项目]`,
    kind: 'project' as const,
  }))
  const uList = userSkills.value.map((s) => ({
    ...s,
    name: `user-${s.name}`,
    rawName: s.name,
    display_name: `${s.display_name || s.name} [个人]`,
    kind: 'user' as const,
  }))
  return [...pList, ...uList]
})

const selectedSkills = ref<ChatSkillMeta[]>([])
const showSkillPicker = ref(false)
const showWindowManager = ref(false)
const chosenPlaceholder = ref('给 Learnova 发送消息...')

function toggleWindowManager(): void {
  showWindowManager.value = !showWindowManager.value
  if (showWindowManager.value) {
    showSkillPicker.value = false
  }
}

function toggleSkillPicker(): void {
  showSkillPicker.value = !showSkillPicker.value
  if (showSkillPicker.value) {
    showWindowManager.value = false
  }
}

function closeAllPreviews(): void {
  activePreviews.value = []
}

// ── 附件状态与处理函数 ───────────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const pendingAttachments = ref<Array<{
  attachment_id?: string
  temp_id: string
  original_filename: string
  mime_type: string
  uploading: boolean
  preview_url?: string
}>>([])

async function loadAttachmentUrls(
  targetAttachments?: AttachmentItem[],
  attachmentIds?: Set<string>,
): Promise<void> {
  if (!currentSession.value) return
  const sidVal = currentSession.value.sid
  const activeImageIds = new Set<string>()
  const atts = targetAttachments || sessionAttachments.value

  const promises = atts
    .filter((att) => att.mime_type.startsWith('image/'))
    .filter((att) => !attachmentIds || attachmentIds.has(att.attachment_id))
    .map(async (att) => {
      activeImageIds.add(att.attachment_id)
      if (!attachmentUrls.value[att.attachment_id]) {
        try {
          const blobUrl = await getAttachmentBlobUrl(sidVal, att.attachment_id)
          attachmentUrls.value[att.attachment_id] = blobUrl
        } catch (error) {
          console.error(`Failed to get blob url for attachment ${att.attachment_id}:`, error)
        }
      }
    })

  await Promise.all(promises)

  if (!attachmentIds) {
    // Clean up unused object URLs when doing a full attachment refresh.
    for (const id of Object.keys(attachmentUrls.value)) {
      if (!activeImageIds.has(id)) {
        URL.revokeObjectURL(attachmentUrls.value[id])
        delete attachmentUrls.value[id]
      }
    }
  }
}

function clearAttachmentUrls(): void {
  for (const url of Object.values(attachmentUrls.value)) {
    URL.revokeObjectURL(url)
  }
  attachmentUrls.value = {}
}

function getMessageImages(message: DisplayMessage): Array<{ url: string; id: string }> {
  if (message.role !== 'user') return []
  if (message.localAttachments && message.localAttachments.length > 0) {
    const images = message.localAttachments.filter((att) => att.mime_type.startsWith('image/'))
    return images.map((att, idx) => {
      const url = (message.previewUrls && message.previewUrls[idx]) || attachmentUrls.value[att.attachment_id] || ''
      return { url, id: att.attachment_id }
    }).filter(img => img.url)
  }
  if (message.previewUrls && message.previewUrls.length > 0) {
    return message.previewUrls.map((url, idx) => ({ url, id: `preview-${idx}` }))
  }
  if (!message.anchor_msg_id) return []
  return sessionAttachments.value
    .filter((att) => att.anchor_msg_id === message.anchor_msg_id && att.mime_type.startsWith('image/'))
    .map((att) => ({
      url: attachmentUrls.value[att.attachment_id],
      id: att.attachment_id,
    }))
    .filter((img): img is { url: string; id: string } => !!img.url)
}

function getMessageFiles(message: DisplayMessage): AttachmentItem[] {
  if (message.role !== 'user') return []
  if (message.localAttachments && message.localAttachments.length > 0) {
    return message.localAttachments.filter((att) => !att.mime_type.startsWith('image/'))
  }
  if (!message.anchor_msg_id) return []
  return sessionAttachments.value.filter(
    (att) => att.anchor_msg_id === message.anchor_msg_id && !att.mime_type.startsWith('image/')
  )
}

function visibleImageAttachmentIds(messages: DisplayMessage[] = visibleMessages.value): Set<string> {
  const ids = new Set<string>()
  for (const message of messages) {
    if (message.role !== 'user' || !message.anchor_msg_id) continue
    for (const att of sessionAttachments.value) {
      if (att.anchor_msg_id === message.anchor_msg_id && att.mime_type.startsWith('image/')) {
        ids.add(att.attachment_id)
      }
    }
  }
  return ids
}

async function refreshVisibleMessageAssets(messages: DisplayMessage[] = visibleMessages.value): Promise<void> {
  await Promise.all([
    refreshVersionMap(messages),
    loadAttachmentUrls(undefined, visibleImageAttachmentIds(messages)),
  ])
}

function getFileType(filename: string, mimeType: string): string {
  const ext = filename.split('.').pop()?.toUpperCase()
  if (ext && ext.length <= 4 && ext !== filename) return ext
  if (mimeType.includes('/')) return mimeType.split('/')[1].toUpperCase()
  return 'FILE'
}

const ALLOWED_MIMES = new Set([
  'image/jpeg', 'image/png', 'image/webp', 'image/gif',
  'text/plain', 'text/markdown', 'text/csv', 'text/html',
  'application/json', 'application/pdf',
])
function triggerFileSelect(): void {
  fileInputRef.value?.click()
}

async function uploadFile(file: File): Promise<void> {
  const limitMB = CHAT_ATTACHMENT_MAX_BYTES / (1024 * 1024)
  if (file.size > CHAT_ATTACHMENT_MAX_BYTES) {
    errorMessage.value = `"${file.name}" 大小超过 ${limitMB}MB 限制`
    return
  }
  const mime = file.type || 'application/octet-stream'
  if (!ALLOWED_MIMES.has(mime)) {
    errorMessage.value = `"${file.name}" 格式不支持（支持：图片、文本、JSON、PDF、CSV）`
    return
  }

  const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2)}`
  const preview_url = mime.startsWith('image/') ? URL.createObjectURL(file) : undefined
  pendingAttachments.value.push({
    temp_id: tempId,
    original_filename: file.name,
    mime_type: mime,
    uploading: true,
    preview_url,
  })
  errorMessage.value = ''

  try {
    const result = await uploadAttachment(sid.value, file)
    const idx = pendingAttachments.value.findIndex((item) => item.temp_id === tempId)
    if (idx !== -1) {
      pendingAttachments.value[idx].attachment_id = result.attachment_id
      pendingAttachments.value[idx].original_filename = result.original_filename
      pendingAttachments.value[idx].uploading = false
    }
  } catch (error) {
    errorMessage.value = `上传"${file.name}"失败：` + getErrorMessage(error)
    if (preview_url) {
      URL.revokeObjectURL(preview_url)
    }
    pendingAttachments.value = pendingAttachments.value.filter((item) => item.temp_id !== tempId)
  }
}

async function handleFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  const files = Array.from(target.files)
  target.value = ''
  await Promise.all(files.map(uploadFile))
}

async function handleComposerPaste(event: ClipboardEvent): Promise<void> {
  const items = event.clipboardData?.items
  if (!items) return
  const fileItems = Array.from(items).filter((item) => item.kind === 'file')
  if (fileItems.length === 0) return
  event.preventDefault()
  const files = fileItems.map((item) => item.getAsFile()).filter((f): f is File => f !== null)
  await Promise.all(files.map(uploadFile))
}

async function removePendingAttachment(att: typeof pendingAttachments.value[0]): Promise<void> {
  if (att.uploading) return
  if (att.attachment_id) {
    try {
      await deleteAttachment(sid.value, att.attachment_id)
    } catch (error) {
      errorMessage.value = '删除附件失败: ' + getErrorMessage(error)
      return
    }
  }
  if (att.preview_url) {
    URL.revokeObjectURL(att.preview_url)
  }
  pendingAttachments.value = pendingAttachments.value.filter((item) => item.temp_id !== att.temp_id)
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function scrollToBottom(force = false): void {
  if (force) stickToBottom.value = true
  if (!stickToBottom.value) return
  setVirtualWindowToBottom()
  nextTick(() => {
    window.requestAnimationFrame(() => {
      const container = chatContainer.value
      if (!container) return
      container.scrollTop = Math.max(0, container.scrollHeight - container.clientHeight)
    })
  })
}

function isChatAtBottom(): boolean {
  const container = chatContainer.value
  if (!container) return true
  return container.scrollHeight - container.scrollTop - container.clientHeight <= CHAT_SCROLL_BOTTOM_THRESHOLD
}

function handleChatScroll(): void {
  stickToBottom.value = isChatAtBottom()
  scheduleVirtualWindowUpdate()
}

function handleWheel(): void {
  scheduleVirtualWindowUpdate()
}

function handleImageLoad(): void {
  if (stickToBottom.value) {
    scrollToBottom()
  }
}

function handleVisualViewportResize(): void {
  scrollToBottom()
}

function knownBlockDigests(): Array<{ block_id: string; digest: string }> {
  return blockIndex.value.map((block) => ({
    block_id: block.block_id,
    digest: block.digest,
  }))
}

function applyFullBlockIndex(response: {
  revision: string
  blocks: MessageBlockIndexItem[]
}): void {
  const previousDigests = new Map(blockIndex.value.map((block) => [block.block_id, block.digest]))
  const nextDigests = new Map(response.blocks.map((block) => [block.block_id, block.digest]))
  messageRevision.value = response.revision
  blockIndex.value = response.blocks
  const activeIds = new Set(response.blocks.map((block) => block.block_id))
  const nextCache: Record<string, DisplayMessage[]> = {}
  for (const [blockId, messages] of Object.entries(blockContentCache.value)) {
    if (activeIds.has(blockId) && previousDigests.get(blockId) === nextDigests.get(blockId)) {
      nextCache[blockId] = messages
    }
  }
  blockContentCache.value = nextCache
  const nextHeights: Record<string, number> = {}
  for (const [blockId, height] of Object.entries(blockHeights.value)) {
    if (activeIds.has(blockId) && previousDigests.get(blockId) === nextDigests.get(blockId)) {
      nextHeights[blockId] = height
    }
  }
  blockHeights.value = nextHeights
}

function applyBlockDelta(response: {
  revision: string
  block_ids: string[]
  upsert: MessageBlockIndexItem[]
  removed: string[]
}): void {
  messageRevision.value = response.revision
  const byId = new Map(blockIndex.value.map((block) => [block.block_id, block]))
  for (const removed of response.removed) {
    byId.delete(removed)
  }
  for (const block of response.upsert) {
    byId.set(block.block_id, block)
  }
  blockIndex.value = response.block_ids
    .map((blockId) => byId.get(blockId))
    .filter((block): block is MessageBlockIndexItem => Boolean(block))

  if (response.removed.length > 0 || response.upsert.length > 0) {
    const activeIds = new Set(blockIndex.value.map((block) => block.block_id))
    const changedIds = new Set(response.upsert.map((block) => block.block_id))
    const nextCache: Record<string, DisplayMessage[]> = {}
    for (const [blockId, messages] of Object.entries(blockContentCache.value)) {
      if (activeIds.has(blockId) && !changedIds.has(blockId)) {
        nextCache[blockId] = messages
      }
    }
    blockContentCache.value = nextCache
    const nextHeights: Record<string, number> = {}
    for (const [blockId, height] of Object.entries(blockHeights.value)) {
      if (activeIds.has(blockId) && !changedIds.has(blockId)) {
        nextHeights[blockId] = height
      }
    }
    blockHeights.value = nextHeights
  }
}

function storeMessageBlocks(blocks: DisplayMessageBlock[]): void {
  if (blocks.length === 0) return
  const next = { ...blockContentCache.value }
  for (const block of blocks) {
    next[block.block_id] = block.messages
  }
  blockContentCache.value = next
}

async function ensureBlockContents(blockIds: string[]): Promise<void> {
  if (!currentSession.value) return
  const missing = blockIds.filter(
    (blockId) => !blockContentCache.value[blockId] && !pendingBlockContentLoads.has(blockId),
  )
  if (missing.length === 0) return
  for (const blockId of missing) pendingBlockContentLoads.add(blockId)
  try {
    const blocks = await getMessageBlocks(currentSession.value.sid, missing)
    storeMessageBlocks(blocks)
  } catch (error) {
    console.error('Failed to load message blocks:', error)
  } finally {
    for (const blockId of missing) pendingBlockContentLoads.delete(blockId)
  }
}

async function ensureVisibleBlockContents(blocks: MessageBlock[] = virtualBlocks.value): Promise<void> {
  await ensureBlockContents(blocks.map((block) => block.id))
}

async function loadMessages(init = false): Promise<void> {
  if (!currentSession.value) return

  const [indexResponse, atts] = await Promise.all([
    init || blockIndex.value.length === 0
      ? listMessageBlockIndex(currentSession.value.sid)
      : syncMessageBlockDelta(currentSession.value.sid, knownBlockDigests()),
    listAttachments(currentSession.value.sid),
  ])

  if ('upsert' in indexResponse) {
    applyBlockDelta(indexResponse)
  } else {
    applyFullBlockIndex(indexResponse)
  }
  sessionAttachments.value = atts

  if (init || stickToBottom.value) {
    setVirtualWindowToBottom()
  } else {
    updateVirtualWindowFromScroll()
  }

  await ensureVisibleBlockContents()
  await refreshVisibleMessageAssets()
  writeChatCache(currentSession.value.sid)

  if (init) {
    scrollToBottom(true)
  } else {
    scrollToBottom()
  }
}

async function refreshVersionMap(
  targetMessages?: DisplayMessage[],
  forceAnchors: Set<string> = new Set(),
): Promise<void> {
  const msgs = targetMessages || visibleMessages.value
  // 收集 messages 中出现的所有 anchor，逐个拉取版本快照
  const anchors = new Set<string>()
  for (const m of msgs) {
    if (m.anchor_msg_id) anchors.add(m.anchor_msg_id)
  }
  const anchorsToFetch = Array.from(anchors).filter(
    (anchor) => forceAnchors.has(anchor) || !versionsByAnchor.value[anchor],
  )
  const next: Record<string, MessageVersionItem[]> = {}
  await Promise.all(
    anchorsToFetch.map(async (anchor) => {
      try {
        const versions = await listMessageVersions(anchor)
        next[anchor] = versions
      } catch {
        // 单个失败不阻断其他
      }
    }),
  )
  versionsByAnchor.value = { ...versionsByAnchor.value, ...next }
  // 第一次见到的 anchor 默认显示位置 = 1
  for (const anchor of anchors) {
    if (!displayedPosByAnchor.value[anchor]) {
      displayedPosByAnchor.value[anchor] = 1
    }
  }
  if (Object.keys(next).length > 0) scheduleChatCacheSave()
}

function anchorVersionCount(anchor?: string | null): number {
  if (!anchor) return 0
  const versions = versionsByAnchor.value[anchor]
  if (!versions) return 0
  // 同一 (anchor, version) 下可能有 user/tool/assistant 多条；按 version 去重再计数
  return new Set(versions.map((v) => v.version)).size
}

function anchorDisplayedPos(anchor?: string | null): number {
  if (!anchor) return 1
  return displayedPosByAnchor.value[anchor] ?? 1
}

function invalidateAnchorVersions(anchor: string): void {
  const next = { ...versionsByAnchor.value }
  delete next[anchor]
  versionsByAnchor.value = next
}

function findCachedMessage(
  predicate: (message: DisplayMessage) => boolean,
): { blockId: string; message: DisplayMessage } | null {
  for (const [blockId, messages] of Object.entries(blockContentCache.value)) {
    const message = messages.find(predicate)
    if (message) return { blockId, message }
  }
  return null
}

function updateCachedMessage(id: string, patch: Partial<DisplayMessage>): void {
  const located = findCachedMessage((message) => message.id === id)
  if (!located) return
  const current = blockContentCache.value[located.blockId] ?? []
  blockContentCache.value = {
    ...blockContentCache.value,
    [located.blockId]: current.map((message) => (
      message.id === id ? { ...message, ...patch } : message
    )),
  }
}

function appendCachedMessageContent(id: string, delta: string): void {
  const located = findCachedMessage((message) => message.id === id)
  if (!located) return
  updateCachedMessage(id, { content: located.message.content + delta })
}

function cachedMessageContent(id: string): string {
  return findCachedMessage((message) => message.id === id)?.message.content ?? ''
}

function addLocalMessageBlock(blockId: string, messages: DisplayMessage[]): void {
  const contentLength = messages.reduce((sum, message) => sum + message.content.length, 0)
  const estimatedHeight = Math.max(92, Math.min(760, 140 + Math.ceil(contentLength / 72) * 22))
  blockIndex.value = [
    ...blockIndex.value,
    {
      block_id: blockId,
      digest: `local-${blockId}`,
      message_ids: messages.map((message) => message.id),
      anchor_msg_id: null,
      roles: messages.map((message) => message.role),
      timestamp: messages[0]?.timestamp ?? Date.now() / 1000,
      content_length: contentLength,
      attachment_count: messages.reduce((sum, message) => sum + (message.localAttachments?.length ?? 0), 0),
      image_attachment_count: messages.reduce(
        (sum, message) => sum + (message.localAttachments?.filter((att) => att.mime_type.startsWith('image/')).length ?? 0),
        0,
      ),
      estimated_height: estimatedHeight,
    },
  ]
  blockContentCache.value = {
    ...blockContentCache.value,
    [blockId]: messages,
  }
}

watch(
  virtualBlocks,
  (blocks) => {
    void ensureVisibleBlockContents(blocks)
  },
  { flush: 'post' },
)

watch(
  visibleMessages,
  (messages) => {
    void refreshVisibleMessageAssets(messages)
  },
  { flush: 'post' },
)

async function regenerateMessage(message: DisplayMessage, newPrompt = ''): Promise<void> {
  if (streaming.value || !currentSession.value || !currentProject.value) return
  if (!message.anchor_msg_id) {
    errorMessage.value = '该消息缺少回合 anchor，无法重放。'
    return
  }

  const anchor = message.anchor_msg_id
  errorMessage.value = ''
  toolStatus.value = ''

  // 找到当前活跃的 user 与 assistant：改 PROMPT 时把 user 气泡先乐观更新成新内容
  const targetUser = findCachedMessage(
    (m) => m.anchor_msg_id === anchor && m.role === 'user',
  )?.message
  const targetAssistant = findCachedMessage(
    (m) => m.anchor_msg_id === anchor && m.role === 'assistant',
  )?.message
  if (newPrompt && targetUser) {
    updateCachedMessage(targetUser.id, { content: newPrompt })
  }
  if (targetAssistant) {
    updateCachedMessage(targetAssistant.id, { content: '', pending: true })
  }

  streaming.value = true
  inflightUserPrompt.value = newPrompt || targetUser?.content || ''
  const abortController = new AbortController()
  currentAbort.value = abortController
  scrollToBottom(true)

  try {
    const done = await regenerateChatMessage(
      currentSession.value.sid,
      currentProject.value.pid,
      anchor,
      newPrompt,
      {
        onTextDelta(delta) {
          if (targetAssistant) {
            appendCachedMessageContent(targetAssistant.id, delta)
            scrollToBottom()
          }
        },
        onToolEvent(event) {
          if (event.type === 'tool_call') {
            toolStatus.value = `正在调用 ${event.tool_name || '工具'}`
          }
          if (event.type === 'tool_result') {
            toolStatus.value = ''
          }
        },
      },
      abortController.signal,
    )

    if (targetAssistant) updateCachedMessage(targetAssistant.id, { pending: false })

    if (done.error) {
      errorMessage.value = done.error_code ? `${done.error_code}: ${done.error}` : done.error
      invalidateAnchorVersions(anchor)
      await loadMessages(false)
      return
    }

    invalidateAnchorVersions(anchor)
    await loadMessages(false)
  } catch (error) {
    if (targetAssistant) updateCachedMessage(targetAssistant.id, { pending: false })
    if (!isAbortError(error)) errorMessage.value = getErrorMessage(error)
    invalidateAnchorVersions(anchor)
    await loadMessages(false)
  } finally {
    streaming.value = false
    toolStatus.value = ''
    currentAbort.value = null
    inflightUserPrompt.value = ''
    scrollToBottom()
  }
}

function openEditPromptDialog(message: DisplayMessage): void {
  if (streaming.value || !message.anchor_msg_id) return
  editDialogAnchor.value = message.anchor_msg_id
  editDialogInitial.value = message.content
  editDialogOpen.value = true
}

async function handleEditPromptSubmit(text: string): Promise<void> {
  const anchor = editDialogAnchor.value
  if (!anchor) return
  const target = findCachedMessage(
    (m) => m.anchor_msg_id === anchor && m.role === 'user',
  )?.message
  editDialogOpen.value = false
  editDialogAnchor.value = null
  editDialogInitial.value = ''
  if (target) await regenerateMessage(target, text)
}

async function openDeleteTurnDialog(message: DisplayMessage): Promise<void> {
  if (streaming.value || !message.anchor_msg_id) return
  const anchor = message.anchor_msg_id
  const confirmed = await confirmDanger({
    title: '删除此回合',
    message: '该回合当前活跃版本（user 与 assistant，含工具调用）将被永久删除。如果之前重放过，历史版本会保留。确定继续吗？',
    confirmText: '删除',
  })
  if (!confirmed) return
  try {
    await deleteTurn(anchor)
    invalidateAnchorVersions(anchor)
    const nextPos = { ...displayedPosByAnchor.value }
    delete nextPos[anchor]
    displayedPosByAnchor.value = nextPos
    await loadMessages(true)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  }
}

async function switchVersion(anchor: string, direction: -1 | 1): Promise<void> {
  if (streaming.value) return
  const versions = versionsByAnchor.value[anchor]
  if (!versions || versions.length === 0) return

  // 按 version 去重并排序：version=0 是活跃版本，1..N-1 是历史版本
  const versionNumbers = Array.from(new Set(versions.map((v) => v.version))).sort((a, b) => a - b)
  const total = versionNumbers.length
  if (total <= 1) return

  const currentPos = displayedPosByAnchor.value[anchor] ?? 1 // 1-based
  const nextPos = ((currentPos - 1 + direction + total) % total) + 1

  // pos 序列：1 → 当前活跃（version=0）；2..total → 历史版本（按 version 升序）
  const historyVersions = versionNumbers.filter((v) => v !== 0)
  const targetVersion = nextPos === 1 ? 0 : historyVersions[nextPos - 2]
  if (targetVersion === 0) {
    // 已经在活跃位，无需 swap
    displayedPosByAnchor.value[anchor] = nextPos
    return
  }

  const target =
    versions.find((v) => v.version === targetVersion && v.kind === 'user') ||
    versions.find((v) => v.version === targetVersion)
  if (!target) return

  try {
    await switchMessageVersion(target.msg_id)
    displayedPosByAnchor.value[anchor] = nextPos
    await loadMessages()
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function updateMessage(id: string, patch: Partial<DisplayMessage>): void {
  updateCachedMessage(id, patch)
}

async function sendMessage(): Promise<void> {
  if (!canSend.value || !currentSession.value || !currentProject.value) return

  const rawContent = draft.value.trim()
  const content = buildPayload(rawContent, selectedSkills.value)
  const now = Date.now() / 1000

  const imagePreviews = pendingAttachments.value
    .filter((att) => att.mime_type.startsWith('image/') && att.preview_url)
    .map((att) => att.preview_url as string)

  const localAttachments: AttachmentItem[] = pendingAttachments.value
    .filter((att) => att.attachment_id)
    .map((att) => ({
      attachment_id: att.attachment_id!,
      anchor_msg_id: null,
      original_filename: att.original_filename,
      mime_type: att.mime_type,
      file_size: 0,
      has_description: false,
      created_at: now,
    }))

  const userMessage: DisplayMessage = {
    id: `local-user-${Date.now()}`,
    role: 'user',
    content: rawContent,
    timestamp: now,
    previewUrls: imagePreviews,
    localAttachments,
  }
  const assistantId = `stream-assistant-${Date.now()}`
  const assistantMessage: DisplayMessage = {
    id: assistantId,
    role: 'assistant',
    content: '',
    timestamp: now,
    pending: true,
  }
  const localBlockId = `local-block-${Date.now()}`

  const attachmentIds = pendingAttachments.value
    .map((att) => att.attachment_id)
    .filter((id): id is string => !!id)

  draft.value = ''
  selectedSkills.value = []
  if (PLACEHOLDERS && PLACEHOLDERS.length > 0) {
    const randomIndex = Math.floor(Math.random() * PLACEHOLDERS.length)
    chosenPlaceholder.value = PLACEHOLDERS[randomIndex]
  }
  pendingAttachments.value = []
  errorMessage.value = ''
  toolStatus.value = ''
  addLocalMessageBlock(localBlockId, [userMessage, assistantMessage])
  streaming.value = true
  inflightUserPrompt.value = rawContent

  const abortController = new AbortController()
  currentAbort.value = abortController
  scrollToBottom(true)

  try {
    const done = await sendChatMessage(
      currentSession.value.sid,
      currentProject.value.pid,
      content,
      {
        onTextDelta(delta) {
          appendCachedMessageContent(assistantId, delta)
          scrollToBottom()
        },
        onToolEvent(event) {
          if (event.type === 'tool_call') {
            toolStatus.value = `正在调用 ${event.tool_name || '工具'}`
          }
          if (event.type === 'tool_result') {
            toolStatus.value = ''
          }
        },
      },
      attachmentIds,
      abortController.signal,
    )

    updateMessage(assistantId, { pending: false })

    if (done.error) {
      updateMessage(assistantId, {
        content: cachedMessageContent(assistantId) || '生成失败。',
      })
      errorMessage.value = done.error_code ? `${done.error_code}: ${done.error}` : done.error
      await loadMessages(false)
      return
    }

    if (done.msg_id) updateMessage(assistantId, { id: done.msg_id })
    await loadMessages(false)
  } catch (error) {
    updateMessage(assistantId, {
      pending: false,
      content: isAbortError(error)
        ? cachedMessageContent(assistantId) || '已停止生成。'
        : cachedMessageContent(assistantId) || '生成失败。',
    })
    if (!isAbortError(error)) errorMessage.value = getErrorMessage(error)
    await loadMessages(false)
  } finally {
    streaming.value = false
    toolStatus.value = ''
    currentAbort.value = null
    inflightUserPrompt.value = ''
    for (const url of imagePreviews) {
      URL.revokeObjectURL(url)
    }
    scrollToBottom()
  }
}

async function stopStreaming(): Promise<void> {
  if (!streaming.value || !currentSession.value || !currentProject.value) return

  const restored = inflightUserPrompt.value

  try {
    await stopChatGeneration(currentSession.value.sid, currentProject.value.pid)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    currentAbort.value?.abort()
    // 把刚才发出去的内容回填到输入框，便于用户继续修改后再发送
    if (restored) {
      const trimmedDraft = draft.value.trim()
      if (trimmedDraft) {
        draft.value = trimmedDraft + '\n' + restored
      } else {
        draft.value = restored
      }
      await nextTick()
      autosizeComposer()
      composerTextarea.value?.focus()
      const len = composerTextarea.value?.value.length ?? 0
      composerTextarea.value?.setSelectionRange(len, len)
    }
  }
}

// 发送快捷键偏好走共享单例，设置中心修改后此处实时生效（不再各自缓存一份）
const { enterMode: sendKeyPref, loadEnterMode } = usePreferences()

const resolvedPlaceholder = computed(() => {
  const base = chosenPlaceholder.value
  if (base === '__SHORTCUT_HINT__') {
    return sendKeyPref.value === 'ctrl_enter'
      ? '给 Learnova 发送消息... (Enter 换行，Ctrl/⌘ + Enter 发送)'
      : '给 Learnova 发送消息... (Enter 发送，Shift + Enter 换行)'
  }
  return base
})

function handleComposerKeydown(event: KeyboardEvent): void {
  if (showSkillPicker.value && (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === 'Escape')) {
    return
  }
  if (sendKeyPref.value === 'ctrl_enter') {
    // Ctrl+Enter sends, plain Enter = newline
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault()
      void sendMessage()
    }
  } else {
    // Enter sends, Shift+Enter = newline
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void sendMessage()
    }
  }
}

function toggleSkill(prefixedName: string): void {
  const skill = allSkills.value.find((s) => s.name === prefixedName)
  if (!skill) return
  const idx = selectedSkills.value.findIndex((s) => s.name === prefixedName)
  if (idx === -1) {
    selectedSkills.value.push(skill)
  } else {
    selectedSkills.value.splice(idx, 1)
  }
}

function removeSkill(prefixedName: string): void {
  selectedSkills.value = selectedSkills.value.filter((s) => s.name !== prefixedName)
}

function checkAtTrigger(): void {
  const el = composerTextarea.value
  if (!el) return
  const pos = el.selectionStart ?? 0
  const before = el.value.slice(0, pos)
  const match = before.match(/(^|[\s\n])@([a-z0-9-]*)$/)
  showSkillPicker.value = Boolean(match)
  if (showSkillPicker.value) {
    showWindowManager.value = false
  }
}

function handleComposerInput(): void {
  checkAtTrigger()
}

function handlePickerToggle(name: string): void {
  toggleSkill(name)
  const el = composerTextarea.value
  if (el) {
    const pos = el.selectionStart ?? 0
    const before = el.value.slice(0, pos)
    const cleaned = before.replace(/(^|[\s\n])@([a-z0-9-]*)$/, '$1')
    if (cleaned !== before) {
      el.value = cleaned + el.value.slice(pos)
      draft.value = el.value
      el.setSelectionRange(cleaned.length, cleaned.length)
    }
  }
}

function buildPayload(text: string, skills: ChatSkillMeta[]): string {
  if (skills.length === 0) return text
  // 后端会为三层技能名各自加前缀（global- / project- / user-）再喂给模型。
  const names = skills.map((s) => `${s.kind}-${s.rawName}`).join('、')
  return `[本轮请优先考虑使用技能：${names}]\n\n${text}`
}

async function copyMessage(id: string, content: string): Promise<void> {
  let ok = false
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(content)
      ok = true
    } catch { /* fall through */ }
  }
  if (!ok) {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = content
      textarea.setAttribute('readonly', '')
      textarea.style.cssText = 'position:fixed;opacity:0'
      document.body.appendChild(textarea)
      textarea.select()
      ok = document.execCommand('copy')
      document.body.removeChild(textarea)
    } catch { /* ignore */ }
  }
  if (ok) {
    copiedId.value = id
    if (copyResetTimer) window.clearTimeout(copyResetTimer)
    copyResetTimer = window.setTimeout(() => { copiedId.value = null }, CHAT_COPY_RESET_MS)
  }
}

function autosizeComposer(): void {
  const el = composerTextarea.value
  if (!el) return
  el.style.height = 'auto'
  const next = Math.min(el.scrollHeight, CHAT_COMPOSER_MAX_HEIGHT)
  el.style.height = `${next}px`
}

// ── Drawer 动画 ─────────────────────────────────────────────────────────────
function onDrawerBeforeEnter(el: Element): void {
  const target = el as HTMLElement
  target.style.maxHeight = '0'
  target.style.opacity = '0'
}

function onDrawerEnter(el: Element, done: () => void): void {
  const target = el as HTMLElement
  requestAnimationFrame(() => {
    target.style.transition = `max-height ${CHAT_DRAWER_ENTER_MAX_HEIGHT_MS}ms ease, opacity ${CHAT_DRAWER_ENTER_OPACITY_MS}ms ease`
    target.style.maxHeight = `${target.scrollHeight}px`
    target.style.opacity = '1'
    const handler = () => { target.removeEventListener('transitionend', handler); done() }
    target.addEventListener('transitionend', handler)
  })
}

function onDrawerAfterEnter(el: Element): void {
  const target = el as HTMLElement
  target.style.maxHeight = ''
  target.style.transition = ''
  target.style.opacity = ''
}

function onDrawerBeforeLeave(el: Element): void {
  const target = el as HTMLElement
  target.style.maxHeight = `${target.scrollHeight}px`
  target.style.opacity = '1'
}

function onDrawerLeave(el: Element, done: () => void): void {
  const target = el as HTMLElement
  requestAnimationFrame(() => {
    target.style.transition = `max-height ${CHAT_DRAWER_LEAVE_MAX_HEIGHT_MS}ms ease, opacity ${CHAT_DRAWER_LEAVE_OPACITY_MS}ms ease`
    target.style.maxHeight = '0'
    target.style.opacity = '0'
    const handler = () => { target.removeEventListener('transitionend', handler); done() }
    target.addEventListener('transitionend', handler)
  })
}

// ── 挂载 / 销毁 ──────────────────────────────────────────────────────────────
async function validateAndLoad(): Promise<void> {
  messagesLoaded.value = false
  resetMessageViewState()
  // 阶段 1：确保项目列表可用，校验 pid 归属（失败 → 退回总览）
  try {
    if (projects.value.length === 0) await loadProjects()
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
    await router.replace({ name: 'overview' })
    return
  }
  if (!currentProject.value) {
    await router.replace({ name: 'overview' })
    return
  }

  // 阶段 2：拉会话列表校验 sid（失败 → 退回科目页，附带错误信息）
  let match: SessionItem | undefined
  try {
    const allSessions = await listSessions(pid.value)
    match = allSessions.find((s) => s.sid === sid.value)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
    await router.replace({ name: 'subject', params: { pid: pid.value } })
    return
  }
  if (!match) {
    await router.replace({ name: 'subject', params: { pid: pid.value } })
    return
  }
  currentSession.value = match

  // 从 localStorage 恢复该会话打开 the 窗口元信息
  const saved = localStorage.getItem(`preview_windows_${match.sid}`)
  if (saved) {
    try {
      const parsed = JSON.parse(saved) as PreviewItem[]
      // Migration: Ensure every restored item has a valid index
      let nextIdx = 1
      for (const item of parsed) {
        if (item.index === undefined || typeof item.index !== 'number') {
          const used = parsed.map((p) => p.index).filter((idx) => idx !== undefined && typeof idx === 'number')
          while (used.includes(nextIdx)) {
            nextIdx++
          }
          item.index = nextIdx
        }
      }
      activePreviews.value = parsed
    } catch (err) {
      console.error('Failed to parse preview windows from localStorage:', err)
      activePreviews.value = []
    }
  } else {
    activePreviews.value = []
  }

  // 先用本地完整缓存同步恢复首屏，再静默从后端刷新。
  applyChatCache(match.sid)

  // 阶段 3：加载消息、项目技能与用户技能。失败不离开视图，只在顶部显示错误，用户可手动重试。
  try {
    await loadMessages(true)
    await loadUserSkills()
    await nextTick()
    messagesLoaded.value = true
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
    messagesLoaded.value = true
  }
  // 项目技能由 useProjectSkills(pidOrNull) 的 watch 自动加载，这里不需要显式调用

  // 阶段 4：消费 SubjectView 传入的初始草稿与附件/技能并自动发送
  const initial = route.query.initial
  if (typeof initial === 'string' && initial.trim()) {
    const state = window.history.state
    if (state && Array.isArray(state.initialSkills)) {
      selectedSkills.value = allSkills.value.filter((s) => state.initialSkills.includes(s.name) || state.initialSkills.includes(s.rawName))
    }
    if (state && Array.isArray(state.initialAttachments)) {
      pendingAttachments.value = state.initialAttachments.map((att: any) => ({
        attachment_id: att.attachment_id,
        temp_id: att.temp_id,
        original_filename: att.original_filename,
        mime_type: att.mime_type,
        uploading: false,
        preview_url: att.preview_url,
      }))
    }
    draft.value = initial
    await router.replace({ name: 'chat', params: { pid: pid.value, sid: sid.value } })
    await nextTick()
    await sendMessage()
  }
}

onMounted(() => {
  void loadEnterMode()
  void validateAndLoad()
  nextTick(autosizeComposer)
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', handleVisualViewportResize)
  }
  if (composerFooter.value) {
    footerResizeObserver = new ResizeObserver(() => {
      if (composerFooter.value) {
        composerHeight.value = composerFooter.value.offsetHeight
      }
    })
    footerResizeObserver.observe(composerFooter.value)
  }
})

onBeforeUnmount(() => {
  currentAbort.value?.abort()
  if (copyResetTimer) window.clearTimeout(copyResetTimer)
  if (saveHeightCacheTimer) {
    window.clearTimeout(saveHeightCacheTimer)
    saveHeightCacheTimer = null
    if (currentSession.value?.sid) writeChatCache(currentSession.value.sid)
  }
  if (virtualScrollRaf !== null) {
    window.cancelAnimationFrame(virtualScrollRaf)
    virtualScrollRaf = null
  }
  virtualResizeObserver?.disconnect()
  virtualResizeObserver = null
  virtualBlockElements.clear()
  for (const att of pendingAttachments.value) {
    if (att.preview_url) {
      URL.revokeObjectURL(att.preview_url)
    }
  }
  clearAttachmentUrls()
  if (window.visualViewport) {
    window.visualViewport.removeEventListener('resize', handleVisualViewportResize)
  }
  if (footerResizeObserver) {
    footerResizeObserver.disconnect()
    footerResizeObserver = null
  }
})

onBeforeRouteLeave(() => {
  messagesLoaded.value = false
})

onBeforeRouteUpdate(() => {
  messagesLoaded.value = false
  // 切换会话时关闭技能编辑框，避免状态残留到新会话
  closeEditor()
})

watch(draft, () => { nextTick(autosizeComposer) })
watch(composerHeight, () => {
  if (stickToBottom.value) {
    scrollToBottom()
  }
})

watch(
  () => currentSession.value?.sessionname,
  (name) => {
    if (name && currentProject.value) {
      document.title = `${currentProject.value.projectname} / ${name} · Learnova`
    }
  },
  { immediate: true },
)

watch(
  () => currentSession.value?.sid,
  (newSid) => {
    if (newSid && PLACEHOLDERS && PLACEHOLDERS.length > 0) {
      const randomIndex = Math.floor(Math.random() * PLACEHOLDERS.length)
      chosenPlaceholder.value = PLACEHOLDERS[randomIndex]
    }
  },
  { immediate: true },
)
</script>

<template>
  <!-- 技能内联编辑器 / 聊天内容切换（带滑入滑出动画） -->
  <Transition name="skill-editor" mode="out-in">
    <SkillEditorPanel
      v-if="editingSkill"
      key="editor"
      :space="editingSkill.space"
      :skill-name="editingSkill.name"
      :display-name="editingSkill.displayName"
      @close="closeEditor"
    />
    <div v-else key="chat" class="absolute inset-0">
    <!-- 消息滚动区铺满整个区域，消息可滚动到浮动 composer 之下（composer 叠在其上层） -->
    <div ref="chatContainer" class="absolute inset-0 overflow-y-auto px-4 pt-16 pb-5 md:px-6" @scroll.passive="handleChatScroll" @wheel.passive="handleWheel" @load.capture="handleImageLoad">
      <!-- 动态预留空间，使最后一条消息可滚动至浮动 composer 上方而不被永久遮挡 -->
      <div class="mx-auto max-w-3xl" :style="{ paddingBottom: `${composerHeight}px` }">
        <div v-if="topSpacerHeight > 0" :style="{ height: `${topSpacerHeight}px` }" aria-hidden="true" />
        <div
          v-for="(block, blockIndex) in virtualBlocks"
          :key="block.id"
          :ref="(el) => setVirtualBlockElement(block.id, el)"
          class="flex w-full flex-col gap-5 chat-turn-block"
          :style="{ marginBottom: virtualStart + blockIndex < messageBlocks.length - 1 ? `${BLOCK_GAP_PX}px` : '0px' }"
        >
          <div
            v-if="block.messages.length === 0"
            :style="{ minHeight: `${blockContentHeight(block)}px` }"
            aria-hidden="true"
          />
          <template v-else>
          <div v-for="message in block.messages" :key="message.id" class="flex w-full flex-col">
          <div v-if="message.role === 'user'" class="group flex justify-end">
            <div class="flex max-w-[85%] flex-col items-end gap-1.5">
              <div v-if="getMessageImages(message).length > 0" class="flex flex-col gap-1.5 items-end">
                <img
                  v-for="img in getMessageImages(message)"
                  :key="img.id"
                  :src="img.url"
                  class="max-w-[240px] max-h-[180px] rounded-2xl object-cover shadow-sm border border-[#d1d5db] cursor-pointer hover:opacity-90 transition-opacity"
                  alt="Uploaded image"
                  @click="openImagePreview(img.url)"
                />
              </div>
              <div v-if="getMessageFiles(message).length > 0" class="flex flex-wrap gap-2 justify-end">
                <div
                  v-for="file in getMessageFiles(message)"
                  :key="file.attachment_id"
                  class="flex items-center gap-2.5 rounded-xl border border-[#d1d5db] bg-white p-3 text-sm text-[#374151] w-[240px] max-w-[240px] shadow-sm"
                >
                  <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gray-50 text-gray-500 border border-gray-100">
                    <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="truncate font-medium text-[#1f2937]" :title="file.original_filename">
                      {{ file.original_filename }}
                    </div>
                    <div class="text-xs text-[#6b7280]">
                      {{ getFileType(file.original_filename, file.mime_type) }}
                    </div>
                  </div>
                </div>
              </div>
              <div class="flex items-end gap-1">
                <button
                  v-if="message.anchor_msg_id && !streaming"
                  class="flex h-7 w-7 items-center justify-center rounded-lg text-[#6b7280] opacity-0 transition-all duration-200 hover:bg-[#e5e7eb] hover:text-[#1f2937] group-hover:opacity-100 active:scale-95"
                  title="编辑后重放"
                  type="button"
                  @click="openEditPromptDialog(message)"
                >
                  <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                    <path d="M12 20h9" />
                    <path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                  </svg>
                </button>
                <button
                  v-if="message.anchor_msg_id && !streaming"
                  class="flex h-7 w-7 items-center justify-center rounded-lg text-[#6b7280] opacity-0 transition-all duration-200 hover:bg-[#fee2e2] hover:text-[#b91c1c] group-hover:opacity-100 active:scale-95"
                  title="删除此回合"
                  type="button"
                  @click="openDeleteTurnDialog(message)"
                >
                  <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                    <path d="M3 6h18" />
                    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  </svg>
                </button>
                <div class="rounded-3xl bg-white px-4 py-2 text-[15px] leading-relaxed text-[#1f2937]">
                  <p class="whitespace-pre-wrap break-words">{{ message.content }}</p>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="group flex w-full min-w-0 flex-col items-start">
            <div class="bg-[#f3f4f6] px-4 py-3 text-[15px] leading-relaxed text-[#1f2937] w-full max-w-full overflow-hidden">
              <MessageContent
                v-if="message.content"
                :content="message.content"
                :streaming="message.pending === true"
                @preview-mermaid="openMermaidPreview"
                @preview-image="openImagePreview"
                @preview-math="openMathPreview"
                @preview-table="openTablePreview"
              />
              <p v-else-if="!message.pending" class="whitespace-pre-wrap break-words text-[#6b7280]">（空响应）</p>
              <div v-if="message.pending" class="mt-3 flex gap-1">
                <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6b7280]" />
                <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6b7280] [animation-delay:120ms]" />
                <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6b7280] [animation-delay:240ms]" />
              </div>
            </div>
            <div v-if="message.content && !message.pending" class="ml-2 mt-1 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <button
                class="flex h-7 w-7 items-center justify-center rounded-lg text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] hover:text-[#1f2937] active:scale-95"
                :title="copiedId === message.id ? '已复制' : '复制'"
                type="button"
                @click="copyMessage(message.id, message.content)"
              >
                <svg v-if="copiedId !== message.id" class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2m-6 12h8a2 2 0 0 1 2-2v-8a2 2 0 0 1-2-2h-8a2 2 0 0 1-2 2v8a2 2 0 0 1 2 2z" />
                </svg>
                <svg v-else class="h-4 w-4 text-[#1f2937]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
              </button>
              <button
                class="flex h-7 w-7 items-center justify-center rounded-lg text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-40 active:scale-95"
                title="重新生成"
                type="button"
                :disabled="streaming || !message.anchor_msg_id"
                @click="regenerateMessage(message)"
              >
                <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6M5.07 9A7 7 0 0 1 19 11M18.93 15A7 7 0 0 1 5 13" />
                </svg>
              </button>
              <template v-if="message.anchor_msg_id && anchorVersionCount(message.anchor_msg_id) > 1">
                <button
                  class="flex h-7 w-7 items-center justify-center rounded-lg text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-40 active:scale-95"
                  title="上一版本"
                  type="button"
                  :disabled="streaming"
                  @click="switchVersion(message.anchor_msg_id, -1)"
                >
                  <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
                <span class="text-xs text-[#6b7280] tabular-nums">
                  {{ anchorDisplayedPos(message.anchor_msg_id) }}/{{ anchorVersionCount(message.anchor_msg_id) }}
                </span>
                <button
                  class="flex h-7 w-7 items-center justify-center rounded-lg text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-40 active:scale-95"
                  title="下一版本"
                  type="button"
                  :disabled="streaming"
                  @click="switchVersion(message.anchor_msg_id, 1)"
                >
                  <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </template>
            </div>
          </div>
          </div>
          </template>
        </div>
        <div v-if="bottomSpacerHeight > 0" :style="{ height: `${bottomSpacerHeight}px` }" aria-hidden="true" />
      </div>
    </div>

    <!-- 浮动 composer：绝对贴底并叠在消息层最上方（z-20）；外层透明且不拦截事件，
         消息可在其下方/周围透出，仅内部 composer 区域接收点击 -->
    <footer ref="composerFooter" class="pointer-events-none absolute inset-x-0 bottom-0 z-20 px-4 pb-4 pt-2 md:px-6 font-hans">
      <div class="pointer-events-auto mx-auto max-w-3xl">
        <p v-if="toolStatus" class="mb-2 text-xs text-[#4b5563]">{{ toolStatus }}</p>

        <Transition
          name="skill-drawer"
          @before-enter="onDrawerBeforeEnter"
          @enter="onDrawerEnter"
          @after-enter="onDrawerAfterEnter"
          @before-leave="onDrawerBeforeLeave"
          @leave="onDrawerLeave"
        >
          <SkillPicker
            v-if="showSkillPicker"
            :skills="allSkills"
            :selected="selectedSkills.map((s) => s.name)"
            @toggle="handlePickerToggle"
            @close="showSkillPicker = false"
          />
          <WindowManager
            v-else-if="showWindowManager"
            :previews="activePreviews"
            @close-preview="closePreview"
            @close-all="closeAllPreviews"
            @focus-preview="focusPreview"
            @toggle-minimize="toggleMinimizePreview"
            @close="showWindowManager = false"
          />
        </Transition>
        <div
          :class="[
            'composer-shell relative bg-white px-4 pt-3.5 pb-2 border border-neutral-200 shadow-sm',
            (showSkillPicker || showWindowManager) ? 'drawer-open' : '',
            streaming ? 'generating' : '',
          ]"
        >
          <SkillChips
            v-if="selectedSkills.length > 0"
            :skills="selectedSkills"
            @remove="removeSkill"
          />

          <!-- Pending Attachments -->
          <div v-if="pendingAttachments.length > 0" class="mb-3 flex flex-wrap gap-2">
            <div
              v-for="att in pendingAttachments"
              :key="att.attachment_id || att.temp_id"
              class="relative flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-2 py-1 text-xs text-[#374151]"
            >
              <img
                v-if="att.preview_url"
                :src="att.preview_url"
                class="h-6 w-6 rounded object-cover flex-shrink-0 cursor-pointer hover:opacity-80 transition-opacity"
                alt="Image preview"
                @click="openImagePreview(att.preview_url)"
              />
              <svg v-else class="h-3.5 w-3.5 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span class="max-w-[120px] truncate" :title="att.original_filename">{{ att.original_filename }}</span>
              <span v-if="att.uploading" class="text-[10px] text-[#9ca3af] animate-pulse">上传中...</span>
              <button
                v-else
                type="button"
                class="flex h-4 w-4 items-center justify-center rounded-full text-[#9ca3af] hover:bg-[#e5e7eb] hover:text-[#1f2937]"
                @click="removePendingAttachment(att)"
              >
                <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <textarea
            ref="composerTextarea"
            v-model="draft"
            :key="currentSession?.sid || 'default'"
            class="composer-textarea w-full resize-none bg-transparent text-sm leading-relaxed outline-none placeholder:text-[#9ca3af] font-hans"
            :disabled="preparing"
            :placeholder="resolvedPlaceholder"
            rows="2"
            @keydown="handleComposerKeydown"
            @input="handleComposerInput"
            @click="checkAtTrigger"
            @paste="handleComposerPaste"
          />
          <!-- mt-1 比原 mt-2 稍小，使图标行更贴近 composer 底部 -->
          <div class="mt-1 flex items-center justify-between">
            <div class="flex items-center gap-1">
              <!-- 上传附件按钮（现在排第一） -->
              <button
                class="flex h-7 w-7 items-center justify-center rounded-full text-[#6b7280] transition hover:bg-[#f3f4f6] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="preparing"
                title="上传附件（图片/文本/PDF，支持多选）"
                type="button"
                @click="triggerFileSelect"
              >
                <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
                </svg>
              </button>

              <!-- 隐藏的文件选择 input，紧跟上传按钮 -->
              <input
                ref="fileInputRef"
                type="file"
                class="hidden"
                multiple
                accept="image/jpeg,image/png,image/webp,image/gif,text/plain,text/markdown,text/csv,application/json,application/pdf"
                @change="handleFileChange"
              />

              <!-- 添加技能按钮（现在排第二） -->
              <button
                class="flex h-7 w-7 items-center justify-center rounded-full text-[#6b7280] transition hover:bg-[#f3f4f6] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-50"
                :class="{ 'bg-neutral-100 text-[#1f2937]': showSkillPicker }"
                :disabled="preparing"
                title="添加技能"
                type="button"
                @click="toggleSkillPicker"
              >
                <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
              </button>

              <!-- 窗口管理按钮（现在排第三） -->
              <button
                class="flex h-7 w-7 items-center justify-center rounded-full text-[#6b7280] transition hover:bg-[#f3f4f6] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-50 relative cursor-pointer"
                :class="{ 'bg-neutral-100 text-[#1f2937]': showWindowManager }"
                :disabled="preparing"
                title="窗口管理"
                type="button"
                @click="toggleWindowManager"
              >
                <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <rect x="3" y="3" width="18" height="18" rx="2" stroke-width="2" />
                  <line x1="3" y1="9" x2="21" y2="9" stroke-width="2" />
                </svg>
                <span
                  v-if="activePreviews.length > 0"
                  class="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-indigo-600 text-[8px] font-bold text-white select-none scale-85 origin-top-right transition-transform"
                >
                  {{ activePreviews.length }}
                </span>
              </button>
            </div>
            <button
              v-if="streaming"
              class="flex h-7.5 items-center justify-center gap-1 rounded-xl border border-[#d1d5db] bg-white px-3 text-[#6b7280] transition hover:border-[#9ca3af] hover:text-[#1f2937]"
              title="停止生成"
              type="button"
              @click="stopStreaming"
            >
              <svg class="h-4.5 w-4.5" aria-hidden="true" fill="currentColor" viewBox="0 0 24 24">
                <path d="M7 7h10v10H7z" />
              </svg>
            </button>
            <button
              v-else
              class="flex h-7.5 w-7.5 items-center justify-center rounded-xl border border-[#d1d5db] bg-transparent text-[#1f2937] transition hover:bg-[#f3f4f6] hover:text-[#111827] disabled:cursor-not-allowed disabled:text-[#9ca3af]"
              :disabled="!canSend"
              title="发送"
              type="button"
              @click="sendMessage"
            >
              <svg class="h-4.5 w-4.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14m0 0-6-6m6 6-6 6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </footer>
    <EditPromptDialog
      v-model="editDialogOpen"
      :initial-text="editDialogInitial"
      :submitting="streaming"
      @submit="handleEditPromptSubmit"
    />
    <MediaPreviewDialog
      v-if="messagesLoaded"
      v-for="(preview, index) in activePreviews"
      v-show="!preview.minimized"
      :key="preview.id"
      :open="true"
      :type="preview.type"
      :source="preview.source"
      :index="preview.index"
      :highlight="highlightedPreviewId === preview.id"
      :stagger-index="index"
      :initial-x="preview.windowX"
      :initial-y="preview.windowY"
      :initial-width="preview.windowWidth"
      :initial-height="preview.windowHeight"
      :dock-left="preview.dockLeft"
      :dock-right="preview.dockRight"
      :dock-top="preview.dockTop"
      :dock-bottom="preview.dockBottom"
      :rel-x="preview.relX"
      :rel-y="preview.relY"
      @close="closePreview(preview.id)"
      @focus="focusPreview(preview.id)"
      @minimize="preview.minimized = true"
      @update-rect="(rect) => updatePreviewRect(preview.id, rect)"
    />
  </div>
  </Transition>
</template>

<style>
/* 技能编辑器滑入/滑出动画：从左侧展开，向右收缩 */
.skill-editor-enter-active {
  transition: transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.25s ease;
}
.skill-editor-leave-active {
  transition: transform 0.25s cubic-bezier(0.4, 0, 1, 1), opacity 0.2s ease;
}
.skill-editor-enter-from {
  transform: translateX(-100%);
  opacity: 0;
}
.skill-editor-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
