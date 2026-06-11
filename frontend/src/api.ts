import { API_BASE_URL, DEFAULT_PROJECT_NAME, DEFAULT_SESSION_NAME, TOKEN_STORAGE_KEY } from './config'

export interface UserOut {
  uuid: string
  username: string
  email: string
  role: string
  self_description: string | null
  major: string | null
  head_file: string | null
  created_at: number
}

export interface AccessTokenOut {
  access_token: string
  token_type: string
}

export interface ProjectItem {
  pid: string
  projectname: string
  timestamp: number
  created_at: number
}

export interface SessionItem {
  sid: string
  sessionname: string
  timestamp: number
  created_at: number
}

export interface MessageItem {
  msg_id: string
  kind: string
  raw_json: string
  timestamp: number
  created_at: number
  anchor_msg_id: string | null
  version: number
}

export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  anchor_msg_id?: string | null
  version?: number
  pending?: boolean
  previewUrls?: string[]
  localAttachments?: AttachmentItem[]
}

export interface ChatWorkspace {
  project: ProjectItem
  session: SessionItem
}

export interface DoneEvent {
  type: 'done'
  msg_id?: string
  anchor_msg_id?: string
  error?: string
  error_code?: string
}

interface ProjectListResponse {
  projects: ProjectItem[]
}

interface SessionListResponse {
  sessions: SessionItem[]
}

interface MessageListResponse {
  messages: MessageItem[]
}

export interface DisplayMessagePage {
  messages: DisplayMessage[]
  rawCount: number
}

interface StreamEvent {
  type: string
  content?: string
  tool_name?: string
  status?: string
  msg_id?: string
  anchor_msg_id?: string
  error?: string
  error_code?: string
}

interface RequestOptions extends RequestInit {
  retryOnUnauthorized?: boolean
  skipAuth?: boolean
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

function notifyTokenChange(token: string | null): void {
  window.dispatchEvent(new CustomEvent('learnova-token-change', { detail: token }))
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  }
  notifyTokenChange(token)
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  const [, payload] = token.split('.')
  if (!payload) return null

  try {
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    return JSON.parse(atob(padded)) as Record<string, unknown>
  } catch {
    return null
  }
}

export function getCurrentUserId(): string | null {
  const token = getStoredToken()
  if (!token) return null

  const payload = decodeJwtPayload(token)
  return typeof payload?.sub === 'string' ? payload.sub : null
}

async function readResponseError(response: Response): Promise<ApiError> {
  let detail: unknown = null
  try {
    const contentType = response.headers.get('content-type') || ''
    detail = contentType.includes('application/json') ? await response.json() : await response.text()
  } catch {
    detail = null
  }

  return new ApiError(getErrorMessage(detail, response.statusText), response.status, detail)
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { retryOnUnauthorized = true, skipAuth = false, ...fetchOptions } = options
  const headers = new Headers(fetchOptions.headers)

  if (!skipAuth) {
    const token = getStoredToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  if (fetchOptions.body !== undefined && !(fetchOptions.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(apiUrl(path), {
    cache: 'no-store',
    ...fetchOptions,
    headers,
    credentials: 'include',
  })

  if (response.status === 401 && !skipAuth && retryOnUnauthorized) {
    try {
      await refreshAccessToken()
      return request<T>(path, { ...fetchOptions, retryOnUnauthorized: false, skipAuth })
    } catch {
      setStoredToken(null)
    }
  }

  if (!response.ok) {
    throw await readResponseError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export async function register(email: string): Promise<{ message: string }> {
  return request<{ message: string }>('/auth/register', {
    method: 'POST',
    skipAuth: true,
    body: JSON.stringify({ email }),
  })
}

export async function setPassword(
  tempToken: string,
  username: string | undefined,
  password: string,
): Promise<AccessTokenOut | undefined> {
  return request<AccessTokenOut>('/auth/set-password', {
    method: 'POST',
    skipAuth: true,
    body: JSON.stringify({ temp_token: tempToken, username, password }),
  })
}

export async function requestPasswordReset(email: string): Promise<{ message: string }> {
  return request<{ message: string }>('/auth/password-reset/request', {
    method: 'POST',
    skipAuth: true,
    body: JSON.stringify({ email }),
  })
}

export async function updateProfile(
  username: string,
  selfDescription: string | null,
  major: string | null,
): Promise<UserOut> {
  return request<UserOut>('/auth/profile', {
    method: 'PUT',
    body: JSON.stringify({ username, self_description: selfDescription, major }),
  })
}

export async function uploadAvatar(file: File): Promise<UserOut> {
  const formData = new FormData()
  formData.append('file', file)
  return request<UserOut>('/auth/avatar', {
    method: 'POST',
    body: formData,
  })
}

export async function login(email: string, password: string): Promise<AccessTokenOut> {
  const token = await request<AccessTokenOut>('/auth/login', {
    method: 'POST',
    skipAuth: true,
    body: JSON.stringify({ email, password }),
  })
  setStoredToken(token.access_token)
  return token
}

export async function refreshAccessToken(): Promise<AccessTokenOut> {
  const token = await request<AccessTokenOut>('/auth/refresh', {
    method: 'POST',
    skipAuth: true,
    retryOnUnauthorized: false,
  })
  setStoredToken(token.access_token)
  return token
}

export async function logout(): Promise<void> {
  try {
    await request<void>('/auth/logout', {
      method: 'POST',
      skipAuth: true,
      retryOnUnauthorized: false,
    })
  } finally {
    setStoredToken(null)
  }
}

export async function getCurrentUser(): Promise<UserOut> {
  return request<UserOut>('/auth/me')
}

export async function listProjects(userId: string): Promise<ProjectItem[]> {
  const response = await request<ProjectListResponse>(`/users/${encodeURIComponent(userId)}/projects`)
  return response.projects
}

export async function createProject(userId: string, projectname: string): Promise<ProjectItem> {
  return request<ProjectItem>(`/users/${encodeURIComponent(userId)}/projects`, {
    method: 'POST',
    body: JSON.stringify({ projectname }),
  })
}

export async function renameProject(pid: string, projectname: string): Promise<ProjectItem> {
  return request<ProjectItem>(`/projects/${encodeURIComponent(pid)}`, {
    method: 'PATCH',
    body: JSON.stringify({ projectname }),
  })
}

export async function deleteProject(pid: string): Promise<void> {
  await request<void>(`/projects/${encodeURIComponent(pid)}`, { method: 'DELETE' })
}

export async function listSessions(pid: string): Promise<SessionItem[]> {
  const response = await request<SessionListResponse>(`/projects/${encodeURIComponent(pid)}/sessions`)
  return response.sessions
}

export async function createSession(pid: string, sessionname: string): Promise<SessionItem> {
  return request<SessionItem>(`/projects/${encodeURIComponent(pid)}/sessions`, {
    method: 'POST',
    body: JSON.stringify({ sessionname }),
  })
}

export async function renameSession(sid: string, sessionname: string): Promise<SessionItem> {
  return request<SessionItem>(`/sessions/${encodeURIComponent(sid)}`, {
    method: 'PATCH',
    body: JSON.stringify({ sessionname }),
  })
}

export async function deleteSession(sid: string): Promise<void> {
  await request<void>(`/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' })
}

export async function ensureChatWorkspace(userId: string): Promise<ChatWorkspace> {
  const projects = await listProjects(userId)
  const project = projects[0] ?? await createProject(userId, DEFAULT_PROJECT_NAME)
  const sessions = await listSessions(project.pid)
  const session = sessions[0] ?? await createSession(project.pid, DEFAULT_SESSION_NAME)
  return { project, session }
}

export async function createNewChatSession(pid: string): Promise<SessionItem> {
  const date = new Date()
  const sessionname = `新对话 ${date.toLocaleDateString('zh-CN')} ${date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })}`
  return createSession(pid, sessionname)
}

function stringifyPartContent(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  return JSON.stringify(value)
}

export function parseMessage(raw: MessageItem): DisplayMessage | null {
  let parsed: { kind?: string; parts?: Array<{ part_kind?: string; content?: unknown }> }

  try {
    parsed = JSON.parse(raw.raw_json) as { kind?: string; parts?: Array<{ part_kind?: string; content?: unknown }> }
  } catch {
    return null
  }

  const parts = Array.isArray(parsed.parts) ? parsed.parts : []
  const meta = {
    anchor_msg_id: raw.anchor_msg_id,
    version: raw.version,
  }

  if (raw.kind === 'user' && parsed.kind === 'request') {
    const content = parts
      .filter((part) => part.part_kind === 'user-prompt')
      .map((part) => stringifyPartContent(part.content))
      .join('\n')
      .trim()

    return content
      ? { id: raw.msg_id, role: 'user', content, timestamp: raw.timestamp, ...meta }
      : null
  }

  if ((raw.kind === 'assistant' || raw.kind === 'agent_response') && parsed.kind === 'response') {
    const content = parts
      .filter((part) => part.part_kind === 'text')
      .map((part) => stringifyPartContent(part.content))
      .join('\n')
      .trim()

    return content
      ? { id: raw.msg_id, role: 'assistant', content, timestamp: raw.timestamp, ...meta }
      : null
  }

  return null
}

export async function listRawMessages(sid: string): Promise<MessageItem[]> {
  const response = await request<MessageListResponse>(`/sessions/${encodeURIComponent(sid)}/messages`)
  return response.messages
}

export async function listDisplayMessages(
  sid: string,
  limit?: number,
  offset?: number
): Promise<DisplayMessage[]> {
  return (await listDisplayMessagePage(sid, limit, offset)).messages
}

export async function listDisplayMessagePage(
  sid: string,
  limit?: number,
  offset?: number
): Promise<DisplayMessagePage> {
  let url = `/sessions/${encodeURIComponent(sid)}/messages`
  const params: string[] = []
  if (limit !== undefined) params.push(`limit=${limit}`)
  if (offset !== undefined) params.push(`offset=${offset}`)
  if (params.length > 0) url += `?${params.join('&')}`

  const response = await request<MessageListResponse>(url)
  return {
    rawCount: response.messages.length,
    messages: response.messages
      .filter((message) => message.version === 0)
      .map(parseMessage)
      .filter((message): message is DisplayMessage => message !== null),
  }
}

export interface MessageBlockIndexItem {
  block_id: string
  digest: string
  message_ids: string[]
  anchor_msg_id: string | null
  roles: Array<'user' | 'assistant'>
  timestamp: number
  content_length: number
  attachment_count: number
  image_attachment_count: number
  estimated_height: number
}

export interface MessageBlockIndexResponse {
  revision: string
  total_blocks: number
  estimated_height: number
  block_ids: string[]
  blocks: MessageBlockIndexItem[]
}

export interface MessageBlockDeltaResponse {
  revision: string
  total_blocks: number
  estimated_height: number
  block_ids: string[]
  upsert: MessageBlockIndexItem[]
  removed: string[]
}

export interface DisplayMessageBlock {
  block_id: string
  messages: DisplayMessage[]
}

export async function listMessageBlockIndex(sid: string): Promise<MessageBlockIndexResponse> {
  return request<MessageBlockIndexResponse>(
    `/sessions/${encodeURIComponent(sid)}/message-block-index`,
  )
}

export async function syncMessageBlockDelta(
  sid: string,
  knownBlocks: Array<{ block_id: string; digest: string }>,
): Promise<MessageBlockDeltaResponse> {
  return request<MessageBlockDeltaResponse>(
    `/sessions/${encodeURIComponent(sid)}/message-block-delta`,
    {
      method: 'POST',
      body: JSON.stringify({ known_blocks: knownBlocks }),
    },
  )
}

export async function getMessageBlocks(
  sid: string,
  blockIds: string[],
): Promise<DisplayMessageBlock[]> {
  if (blockIds.length === 0) return []
  const response = await request<{ revision: string; blocks: Array<{ block_id: string; messages: MessageItem[] }> }>(
    `/sessions/${encodeURIComponent(sid)}/message-blocks`,
    {
      method: 'POST',
      body: JSON.stringify({ block_ids: blockIds }),
    },
  )
  return response.blocks.map((block) => ({
    block_id: block.block_id,
    messages: block.messages
      .map(parseMessage)
      .filter((message): message is DisplayMessage => message !== null),
  }))
}

export interface MessageVersionItem {
  msg_id: string
  kind: string
  raw_json: string
  anchor_msg_id: string | null
  version: number
  timestamp: number
  created_at: number
}

interface MessageVersionsResponse {
  versions: MessageVersionItem[]
}

export async function listMessageVersions(anchorMsgId: string): Promise<MessageVersionItem[]> {
  const response = await request<MessageVersionsResponse>(
    `/messages/${encodeURIComponent(anchorMsgId)}/versions`,
  )
  return response.versions
}

interface SwitchVersionResponse {
  success: boolean
  switched_msg_id: string
}

export async function switchMessageVersion(targetVersionMsgId: string): Promise<SwitchVersionResponse> {
  return request<SwitchVersionResponse>(
    `/messages/${encodeURIComponent(targetVersionMsgId)}/switch-version`,
    {
      method: 'POST',
      body: JSON.stringify({ target_version_msg_id: targetVersionMsgId }),
    },
  )
}

export async function deleteTurn(anchorMsgId: string): Promise<void> {
  await request<void>(
    `/messages/${encodeURIComponent(anchorMsgId)}/turn`,
    { method: 'DELETE' },
  )
}

function createNonce(): string {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function parseSseFrame(frame: string): StreamEvent | null {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')

  if (!data) return null

  try {
    return JSON.parse(data) as StreamEvent
  } catch {
    return null
  }
}

async function streamLoop(
  sid: string,
  payload: {
    pid: string
    action: 'send' | 'regenerate' | 'stop'
    message?: string
    anchor_msg_id?: string | null
    attachment_ids?: string[] | null
  },
  callbacks: {
    onTextDelta?: (content: string) => void
    onToolEvent?: (event: StreamEvent) => void
    onDone?: (event: DoneEvent) => void
  } = {},
  signal?: AbortSignal,
  retryOnUnauthorized = true,
): Promise<DoneEvent> {
  const headers = new Headers({
    'Content-Type': 'application/json',
    'X-Nonce': createNonce(),
    'X-Nonce-Timestamp': String(Date.now() / 1000),
  })
  const token = getStoredToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(apiUrl(`/loop/${encodeURIComponent(sid)}`), {
    method: 'POST',
    headers,
    credentials: 'include',
    signal,
    body: JSON.stringify(payload),
  })

  if (response.status === 401 && retryOnUnauthorized) {
    await refreshAccessToken()
    return streamLoop(sid, payload, callbacks, signal, false)
  }

  if (!response.ok) {
    throw await readResponseError(response)
  }

  if (!response.body) {
    throw new ApiError('后端没有返回可读取的 SSE 响应。', response.status, null)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    let separatorIndex = buffer.indexOf('\n\n')
    while (separatorIndex !== -1) {
      const frame = buffer.slice(0, separatorIndex)
      buffer = buffer.slice(separatorIndex + 2)

      const event = parseSseFrame(frame)
      if (event?.type === 'text_delta' && typeof event.content === 'string') {
        callbacks.onTextDelta?.(event.content)
      } else if (event?.type === 'tool_call' || event?.type === 'tool_result') {
        callbacks.onToolEvent?.(event)
      } else if (event?.type === 'done') {
        const doneEvent: DoneEvent = {
          type: 'done',
          msg_id: event.msg_id,
          anchor_msg_id: event.anchor_msg_id,
          error: event.error,
          error_code: event.error_code,
        }
        callbacks.onDone?.(doneEvent)
        return doneEvent
      }

      separatorIndex = buffer.indexOf('\n\n')
    }
  }

  const closedEvent: DoneEvent = {
    type: 'done',
    error: 'SSE stream ended before a done event.',
    error_code: 'STREAM_CLOSED',
  }
  callbacks.onDone?.(closedEvent)
  return closedEvent
}

export async function sendChatMessage(
  sid: string,
  pid: string,
  message: string,
  callbacks: {
    onTextDelta: (content: string) => void
    onToolEvent?: (event: StreamEvent) => void
    onDone?: (event: DoneEvent) => void
  },
  attachmentIds?: string[] | null,
  signal?: AbortSignal,
): Promise<DoneEvent> {
  return streamLoop(sid, { pid, action: 'send', message, attachment_ids: attachmentIds }, callbacks, signal)
}

export async function regenerateChatMessage(
  sid: string,
  pid: string,
  anchorMsgId: string,
  message: string,
  callbacks: {
    onTextDelta: (content: string) => void
    onToolEvent?: (event: StreamEvent) => void
    onDone?: (event: DoneEvent) => void
  },
  signal?: AbortSignal,
): Promise<DoneEvent> {
  return streamLoop(
    sid,
    { pid, action: 'regenerate', anchor_msg_id: anchorMsgId, message },
    callbacks,
    signal,
  )
}

export async function stopChatGeneration(sid: string, pid: string): Promise<void> {
  await streamLoop(sid, { pid, action: 'stop', message: '' })
}

// ── 通用文件 API ────────────────────────────────────────────────────────────────

export type FileSpace =
  | { kind: 'user'; userId: string }
  | { kind: 'project'; pid: string }

export interface FileEntry {
  name: string
  is_dir: boolean
  rel_path: string
  size: number
  updated_at: number
}

interface FileListResponse {
  path: string
  entries: FileEntry[]
}

interface FileContentResponse {
  path: string
  content: string
  size: number
  updated_at: number
}

function fileBasePath(space: FileSpace): string {
  return space.kind === 'user'
    ? `/users/${encodeURIComponent(space.userId)}/files`
    : `/projects/${encodeURIComponent(space.pid)}/files`
}

export async function listFiles(space: FileSpace, path = '.'): Promise<FileEntry[]> {
  const base = fileBasePath(space)
  const res = await request<FileListResponse>(`${base}?path=${encodeURIComponent(path)}`)
  return res.entries
}

export async function readFile(
  space: FileSpace,
  path: string,
): Promise<{ path: string; content: string; size: number; updated_at: number }> {
  const base = fileBasePath(space)
  return request<FileContentResponse>(`${base}/content?path=${encodeURIComponent(path)}`)
}

export async function writeFile(
  space: FileSpace,
  path: string,
  content: string,
): Promise<{ path: string; size: number; updated_at: number }> {
  const base = fileBasePath(space)
  return request<FileContentResponse>(base, {
    method: 'PUT',
    body: JSON.stringify({ path, content }),
  })
}

export async function deleteFile(space: FileSpace, path: string): Promise<void> {
  const base = fileBasePath(space)
  return request<void>(`${base}?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
}

export async function createDirectory(space: FileSpace, path: string): Promise<void> {
  const base = fileBasePath(space)
  return request<void>(`${base}/directories`, {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
}

// ── 用户模型配置 ────────────────────────────────────────────────────────────────

export interface ModelConfigItem {
  config_id: string
  config_name: string
  api_key: string
  base_url: string
  model_name: string
  user_instruction: string
  temperature: number | null
  max_tokens: number | null
  is_active: boolean
  supports_vision: boolean
  created_at: number
  updated_at: number
}

export interface ModelConfigListResponse {
  configs: ModelConfigItem[]
}

export interface CreateModelConfigRequest {
  config_name: string
  api_key?: string
  base_url?: string
  model_name?: string
  user_instruction?: string
  temperature?: number | null
  max_tokens?: number | null
  is_active?: boolean
  supports_vision?: boolean
}

export interface UpdateModelConfigRequest {
  config_name?: string
  api_key?: string
  base_url?: string
  model_name?: string
  user_instruction?: string
  temperature?: number | null
  max_tokens?: number | null
  supports_vision?: boolean
}

export interface ActiveConfigResponse {
  config: ModelConfigItem | null
  configs: ModelConfigItem[]
}

export interface TestConnectionRequest {
  api_key?: string
  base_url?: string
  model_name?: string
  supports_vision?: boolean
}

export interface TestConnectionResponse {
  success: boolean
  message: string
  model: string | null
}

export async function listModelConfigs(): Promise<ModelConfigItem[]> {
  const response = await request<ModelConfigListResponse>('/settings/model-configs')
  return response.configs
}

export async function createModelConfig(payload: CreateModelConfigRequest): Promise<ModelConfigItem> {
  return request<ModelConfigItem>('/settings/model-configs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function getActiveModelConfig(): Promise<ActiveConfigResponse> {
  return request<ActiveConfigResponse>('/settings/model-configs/active')
}

export async function updateModelConfig(configId: string, payload: UpdateModelConfigRequest): Promise<ModelConfigItem> {
  return request<ModelConfigItem>(`/settings/model-configs/${encodeURIComponent(configId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function activateModelConfig(configId: string): Promise<ModelConfigItem> {
  return request<ModelConfigItem>(`/settings/model-configs/${encodeURIComponent(configId)}/activate`, {
    method: 'POST',
  })
}

export async function deactivateAllModelConfigs(): Promise<void> {
  await request<void>('/settings/model-configs/deactivate', { method: 'POST' })
}

export async function deleteModelConfig(configId: string): Promise<void> {
  await request<void>(`/settings/model-configs/${encodeURIComponent(configId)}`, { method: 'DELETE' })
}

export async function testConnectionWithParams(payload: TestConnectionRequest): Promise<TestConnectionResponse> {
  return request<TestConnectionResponse>('/settings/model-configs/test-connection', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function testConnectionWithConfig(configId: string, payload?: TestConnectionRequest): Promise<TestConnectionResponse> {
  return request<TestConnectionResponse>(`/settings/model-configs/${encodeURIComponent(configId)}/test-connection`, {
    method: 'POST',
    ...(payload ? { body: JSON.stringify(payload) } : {}),
  })
}

export interface FetchModelsRequest {
  api_key?: string
  base_url?: string
}

export interface FetchModelsResponse {
  success: boolean
  models: string[]
  message: string
}

export async function fetchModels(payload: FetchModelsRequest): Promise<FetchModelsResponse> {
  return request<FetchModelsResponse>('/settings/model-configs/fetch-models', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ── 社区技能广场 ────────────────────────────────────────────────────────────────

export type CommunitySort = 'popular' | 'newest' | 'most_liked'

export interface CommunitySkillSummary {
  id: string
  owner_uuid: string
  owner_username?: string
  name: string
  display_name: string | null
  description: string
  likes: number
  downloads: number
  liked_by_me?: boolean
  latest_version?: string | null
  version?: string | null
  tags?: string | null
  size_bytes: number
  created_at: number
  updated_at: number
}

/** 社区技能详情（含 README、贡献者、版本列表、当前用户点赞状态）
 *  注意：后端详情接口的 latest_version 是完整版本对象，列表接口的是字符串 */
export interface CommunitySkillDetail extends Omit<CommunitySkillSummary, 'latest_version'> {
  readme_md?: string
  liked_by_me: boolean
  latest_version?: CommunitySkillVersion | null
  contributors?: CommunityContributor[]
  versions?: CommunitySkillVersion[]
}

export interface CommunitySkillListResponse {
  skills: CommunitySkillSummary[]
  total: number
}

export interface CommunityContributor {
  skill_id: string
  user_uuid: string
  role: string
  created_at: number
  /** 后端 join 返回的用户名 */
  username?: string
}

export interface CommunitySkillVersion {
  id: string
  skill_id: string
  version: string
  readme_md: string
  changelog: string
  tags: string
  archive_path: string
  size_bytes: number
  downloads: number
  status: string
  submitted_by: string
  created_at: number
  skill_name?: string
}

export interface ReviewLog {
  id: string
  version_id: string
  reviewer_uuid: string
  action: string
  from_status: string
  to_status: string
  note: string
  created_at: number
}

export interface CommunityComment {
  id: string
  skill_id: string
  user_uuid: string
  /** 后端 join 返回的用户名 */
  username?: string
  content: string
  parent_id: string | null
  depth: number
  reply_to_uuid: string | null
  /** 被回复者的用户名 */
  reply_to_username?: string
  likes: number
  liked_by_me?: boolean
  created_at: number
  updated_at: number
  /** 前端组装：子回复列表 */
  replies?: CommunityComment[]
}

export interface CommunityCommentListResponse {
  comments: CommunityComment[]
}

export interface InstallResponse {
  name: string
  skill_id: string
  downloads: number
}

export interface InstallSkillRequest {
  target: 'user' | 'project' | 'library'
  pid?: string
  version_id?: string
}

function nonceHeaders(): Record<string, string> {
  return {
    'X-Nonce': crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    'X-Nonce-Timestamp': String(Date.now() / 1000),
  }
}

// ── API 函数 ──────────────────────────────────────────────────────────────────

export async function listCommunitySkills(params: {
  keyword?: string
  limit?: number
  offset?: number
  sort?: CommunitySort
  tags?: string[]
} = {}): Promise<CommunitySkillListResponse> {
  const search = new URLSearchParams()
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  search.set('sort', params.sort ?? 'popular')
  if (params.tags && params.tags.length > 0) {
    for (const t of params.tags) search.append('tag', t)
  }
  return request<CommunitySkillListResponse>(`/community/skills?${search.toString()}`)
}

export async function getCommunitySkill(id: string): Promise<CommunitySkillDetail> {
  return request<CommunitySkillDetail>(`/community/skills/${encodeURIComponent(id)}`)
}

export async function likeCommunitySkill(id: string): Promise<{ liked: boolean }> {
  return request<{ liked: boolean }>(`/community/skills/${encodeURIComponent(id)}/like`, {
    method: 'POST',
  })
}

export async function publishCommunitySkill(skillName: string): Promise<CommunitySkillDetail> {
  return request<CommunitySkillDetail>('/community/skills', {
    method: 'POST',
    headers: nonceHeaders(),
    body: JSON.stringify({ skill_name: skillName }),
  })
}

export async function installCommunitySkill(id: string, payload?: InstallSkillRequest): Promise<InstallResponse> {
  return request<InstallResponse>(`/community/skills/${encodeURIComponent(id)}/install`, {
    method: 'POST',
    headers: nonceHeaders(),
    body: payload ? JSON.stringify(payload) : undefined,
  })
}

export async function deleteCommunitySkill(id: string): Promise<void> {
  await request<void>(`/community/skills/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

// ── 社区评论 ──────────────────────────────────────────────────────────────────

export async function listCommunityComments(
  skillId: string,
  params: { parent_id?: string; limit?: number; offset?: number } = {},
): Promise<CommunityComment[]> {
  const search = new URLSearchParams()
  if (params.parent_id) search.set('parent_id', params.parent_id)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  return request<CommunityComment[]>(
    `/community/skills/${encodeURIComponent(skillId)}/comments?${search.toString()}`,
  )
}

export async function createCommunityComment(
  skillId: string,
  payload: { content: string; parent_id?: string | null; reply_to_uuid?: string | null },
): Promise<CommunityComment> {
  return request<CommunityComment>(`/community/skills/${encodeURIComponent(skillId)}/comments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function deleteCommunityComment(skillId: string, commentId: string): Promise<void> {
  await request<void>(`/community/skills/${encodeURIComponent(skillId)}/comments/${encodeURIComponent(commentId)}`, {
    method: 'DELETE',
  })
}

export async function likeCommunityComment(commentId: string): Promise<{ liked: boolean }> {
  return request<{ liked: boolean }>(`/community/comments/${encodeURIComponent(commentId)}/like`, {
    method: 'POST',
  })
}

export async function reportCommunityComment(
  commentId: string,
  payload: { reason: string; detail?: string },
): Promise<{ id: string; status: string }> {
  return request<{ id: string; status: string }>(
    `/community/comments/${encodeURIComponent(commentId)}/report`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

// ── 社区版本 ──────────────────────────────────────────────────────────────────

export async function listCommunityVersions(skillId: string): Promise<CommunitySkillVersion[]> {
  return request<CommunitySkillVersion[]>(
    `/community/skills/${encodeURIComponent(skillId)}/versions`,
  )
}

/** 列出社区技能指定版本的文件 */
export async function listCommunitySkillFiles(
  skillId: string,
  versionId: string,
  path: string = '.',
): Promise<{ path: string; entries: LibraryFileEntry[] }> {
  const params = new URLSearchParams({ path })
  return request<{ path: string; entries: LibraryFileEntry[] }>(
    `/community/skills/${encodeURIComponent(skillId)}/versions/${encodeURIComponent(versionId)}/files?${params}`,
  )
}

/** 读取社区技能指定版本的文件内容 */
export async function readCommunitySkillFileContent(
  skillId: string,
  versionId: string,
  path: string,
): Promise<{ path: string; content: string }> {
  const params = new URLSearchParams({ path })
  return request<{ path: string; content: string }>(
    `/community/skills/${encodeURIComponent(skillId)}/versions/${encodeURIComponent(versionId)}/files/content?${params}`,
  )
}

// ── 社区排行榜 ────────────────────────────────────────────────────────────────

export async function getCommunityLeaderboard(limit = 10): Promise<CommunitySkillSummary[]> {
  const search = new URLSearchParams()
  search.set('limit', String(limit))
  const response = await request<{ skills: CommunitySkillSummary[] }>(
    `/community/leaderboard?${search.toString()}`,
  )
  return response.skills
}

// ── 社区审核 ──────────────────────────────────────────────────────────────────

export async function listOwnerReviews(): Promise<CommunitySkillVersion[]> {
  return request<CommunitySkillVersion[]>('/owner/reviews')
}

export async function approveOwnerReview(versionId: string, note = ''): Promise<ReviewLog> {
  return request<ReviewLog>(`/owner/reviews/${encodeURIComponent(versionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  })
}

export async function rejectOwnerReview(versionId: string, note = ''): Promise<ReviewLog> {
  return request<ReviewLog>(`/owner/reviews/${encodeURIComponent(versionId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  })
}

export async function listAdminReviews(): Promise<CommunitySkillVersion[]> {
  return request<CommunitySkillVersion[]>('/admin/reviews')
}

export async function approveAdminReview(versionId: string, note = ''): Promise<ReviewLog> {
  return request<ReviewLog>(`/admin/reviews/${encodeURIComponent(versionId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  })
}

export async function rejectAdminReview(versionId: string, note = ''): Promise<ReviewLog> {
  return request<ReviewLog>(`/admin/reviews/${encodeURIComponent(versionId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  })
}

// ── 仓库技能 ──────────────────────────────────────────────────────────────────

export interface UserLibrarySkill {
  id: string
  user_uuid: string
  name: string
  display_name: string | null
  description: string
  readme_md: string
  tags: string
  version: string
  changelog: string
  source: 'runtime' | 'zip' | 'community' | 'fork'
  community_skill_id: string | null
  local_path: string
  size_bytes: number
  created_at: number
  updated_at: number
}

export async function uploadLibrarySkillZip(file: File): Promise<UserLibrarySkill> {
  return request<UserLibrarySkill>('/library/skills/upload', {
    method: 'POST',
    headers: {
      ...nonceHeaders(),
      'Content-Type': 'application/zip',
    },
    body: file,
  })
}

export interface LibrarySkillListResponse {
  skills: UserLibrarySkill[]
  total: number
  limit: number
  offset: number
  sort: string
}

export type LibrarySkillSort = 'newest' | 'oldest' | 'name-asc' | 'name-desc'

/** 获取当前用户的仓库技能列表，支持筛选/排序/分页 */
export async function listLibrarySkills(params: {
  keyword?: string
  tag?: string[]
  sort?: LibrarySkillSort
  limit?: number
  offset?: number
} = {}): Promise<LibrarySkillListResponse> {
  const search = new URLSearchParams()
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.tag && params.tag.length > 0) {
    for (const t of params.tag) search.append('tag', t)
  }
  if (params.sort) search.set('sort', params.sort)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  return request<LibrarySkillListResponse>(`/library/skills?${search.toString()}`)
}

/** 获取单条仓库技能详情 */
export async function getLibrarySkill(libraryId: string): Promise<UserLibrarySkill> {
  return request<UserLibrarySkill>(`/library/skills/${encodeURIComponent(libraryId)}`)
}

export interface LibraryPublishForm {
  library_skill: UserLibrarySkill
  community_skill: CommunitySkillSummary | null
  latest_approved_version: CommunitySkillVersion | null
  suggested_version: string
}

/** 获取仓库技能发布到社区的表单预填数据 */
export async function getLibraryPublishForm(libraryId: string): Promise<LibraryPublishForm> {
  return request<LibraryPublishForm>(`/library/skills/${encodeURIComponent(libraryId)}/publish-form`)
}

/** 将仓库技能提交到社区审核流 */
export async function publishLibrarySkill(
  libraryId: string,
  payload: { version: string; changelog: string },
): Promise<CommunitySkillVersion> {
  return request<CommunitySkillVersion>(`/library/skills/${encodeURIComponent(libraryId)}/publish`, {
    method: 'POST',
    headers: nonceHeaders(),
    body: JSON.stringify(payload),
  })
}

/** 将仓库技能安装到运行层 */
export async function installLibrarySkill(
  libraryId: string,
  payload: { target: 'user' | 'project'; pid?: string | null },
): Promise<{ name: string; target: string; installed: boolean }> {
  return request<{ name: string; target: string; installed: boolean }>(
    `/library/skills/${encodeURIComponent(libraryId)}/install`,
    {
      method: 'POST',
      headers: nonceHeaders(),
      body: JSON.stringify(payload),
    },
  )
}

/** Fork 仓库技能，可选覆盖元数据 */
export async function forkLibrarySkill(
  libraryId: string,
  overrides?: { name?: string; display_name?: string; description?: string; readme_md?: string; tags?: string },
): Promise<UserLibrarySkill> {
  return request<UserLibrarySkill>(`/library/skills/${encodeURIComponent(libraryId)}/fork`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...nonceHeaders() },
    body: JSON.stringify(overrides ?? {}),
  })
}

/** 仓库技能文件列表条目 */
export interface LibraryFileEntry {
  name: string
  rel_path: string
  is_dir: boolean
  size: number
}

/** 列出仓库技能的文件 */
export async function listLibrarySkillFiles(
  libraryId: string,
  path: string = '.',
): Promise<{ path: string; entries: LibraryFileEntry[] }> {
  const params = new URLSearchParams({ path })
  return request<{ path: string; entries: LibraryFileEntry[] }>(
    `/library/skills/${encodeURIComponent(libraryId)}/files?${params}`,
  )
}

/** 读取仓库技能的文件内容 */
export async function readLibrarySkillFileContent(
  libraryId: string,
  path: string,
): Promise<{ path: string; content: string }> {
  const params = new URLSearchParams({ path })
  return request<{ path: string; content: string }>(
    `/library/skills/${encodeURIComponent(libraryId)}/files/content?${params}`,
  )
}

/** 收集本地技能到仓库 */
export async function collectLibrarySkill(payload: {
  skill_name: string
  template_id?: string | null
  name?: string | null
  display_name?: string | null
  description?: string | null
  readme_md?: string | null
  tags?: string | null
}): Promise<UserLibrarySkill> {
  return request<UserLibrarySkill>('/library/skills/collect', {
    method: 'POST',
    headers: nonceHeaders(),
    body: JSON.stringify(payload),
  })
}

/** 获取同名已入库的模板匹配建议 */
export async function matchLibrarySkillTemplate(skillName: string): Promise<{
  skill_name: string
  matched: UserLibrarySkill | null
}> {
  return request<{ skill_name: string; matched: UserLibrarySkill | null }>(
    `/library/skills/match-template?skill_name=${encodeURIComponent(skillName)}`
  )
}

/** 读取运行层技能配置以辅助填充表单 */
export async function parseRuntimeSkill(skillName: string): Promise<{
  frontmatter: any
  readme_md?: string
  latest_in_library: UserLibrarySkill | null
}> {
  return request<{ frontmatter: any; readme_md?: string; latest_in_library: UserLibrarySkill | null }>(
    `/library/skills/parse-runtime?skill_name=${encodeURIComponent(skillName)}`
  )
}

/** 更新仓库技能的展示元数据 */
export async function updateLibrarySkillMeta(
  libraryId: string,
  payload: {
    name?: string | null
    display_name?: string | null
    description?: string | null
    readme_md?: string | null
    tags?: string | null
  }
): Promise<UserLibrarySkill> {
  return request<UserLibrarySkill>(`/library/skills/${encodeURIComponent(libraryId)}/meta`, {
    method: 'PUT',
    headers: nonceHeaders(),
    body: JSON.stringify(payload),
  })
}

/** 删除单条仓库技能 */
export async function deleteLibrarySkill(libraryId: string): Promise<void> {
  await request<void>(`/library/skills/${encodeURIComponent(libraryId)}`, {
    method: 'DELETE',
  })
}

/** 批量删除仓库技能 */
export async function bulkDeleteLibrarySkills(skillIds: string[]): Promise<{ deleted: number }> {
  return request<{ deleted: number }>('/library/skills/bulk-delete', {
    method: 'POST',
    headers: nonceHeaders(),
    body: JSON.stringify({ skill_ids: skillIds }),
  })
}

// ─── 账号设置 ──────────────────────────────────────────────────────────────

export interface AccountInfo {
  uuid: string
  username: string
  email: string
  created_at: number
}

export interface UpdateUsernameRequest {
  username: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

export async function getAccountInfo(): Promise<AccountInfo> {
  return request<AccountInfo>('/settings/account')
}

export async function updateUsername(payload: UpdateUsernameRequest): Promise<AccountInfo> {
  return request<AccountInfo>('/settings/account/username', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function changePassword(payload: ChangePasswordRequest): Promise<void> {
  await request<void>('/settings/account/change-password', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

// ─── 偏好设置 ──────────────────────────────────────────────────────────────

export interface Preferences {
  enter_mode: string
  updated_at: number | null
}

export interface UpdatePreferencesRequest {
  enter_mode?: string
}

export async function getPreferences(): Promise<Preferences> {
  return request<Preferences>('/settings/preferences')
}

export async function updatePreferences(payload: UpdatePreferencesRequest): Promise<Preferences> {
  return request<Preferences>('/settings/preferences', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

// ── 附件 API ────────────────────────────────────────────────────────────────

export interface AttachmentUploadResult {
  attachment_id: string
  original_filename: string
  mime_type: string
  file_size: number
  created_at: number
}

export interface AttachmentItem {
  attachment_id: string
  anchor_msg_id: string | null
  original_filename: string
  mime_type: string
  file_size: number
  has_description: boolean
  created_at: number
}

export interface AttachmentListResponse {
  attachments: AttachmentItem[]
}

export async function uploadAttachment(
  sid: string,
  file: File,
): Promise<AttachmentUploadResult> {
  const formData = new FormData()
  formData.append('file', file)
  return request<AttachmentUploadResult>(`/sessions/${encodeURIComponent(sid)}/attachments`, {
    method: 'POST',
    body: formData,
  })
}

export async function listAttachments(sid: string): Promise<AttachmentItem[]> {
  const data = await request<AttachmentListResponse>(`/sessions/${encodeURIComponent(sid)}/attachments`)
  return data.attachments
}

export async function deleteAttachment(sid: string, attachmentId: string): Promise<void> {
  await request<void>(`/sessions/${encodeURIComponent(sid)}/attachments/${encodeURIComponent(attachmentId)}`, {
    method: 'DELETE',
  })
}

export async function getAttachmentBlobUrl(sid: string, attachmentId: string): Promise<string> {
  const url = apiUrl(`/sessions/${encodeURIComponent(sid)}/attachments/${encodeURIComponent(attachmentId)}`)
  const makeRequest = async (token: string | null) => {
    const headers = new Headers()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    return fetch(url, { headers })
  }

  let token = getStoredToken()
  let response = await makeRequest(token)

  if (response.status === 401) {
    try {
      const refreshed = await refreshAccessToken()
      token = refreshed.access_token
      response = await makeRequest(token)
    } catch {
      setStoredToken(null)
    }
  }

  if (!response.ok) {
    throw await readResponseError(response)
  }

  const blob = await response.blob()
  return URL.createObjectURL(blob)
}


// ── 错误处理 ────────────────────────────────────────────────────────────────────

export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后重试。'): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  if (typeof error === 'string' && error.trim()) return error

  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = (error as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (typeof detail === 'object' && detail !== null && 'message' in detail) {
      const message = (detail as { message: unknown }).message
      if (typeof message === 'string') return message
    }
  }

  return fallback
}
