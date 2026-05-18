const TOKEN_STORAGE_KEY = 'teachi.access_token'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export interface UserOut {
  uuid: string
  username: string
  email: string
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
  window.dispatchEvent(new CustomEvent('teachi-token-change', { detail: token }))
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

export async function register(username: string, email: string, password: string): Promise<UserOut> {
  return request<UserOut>('/auth/register', {
    method: 'POST',
    skipAuth: true,
    body: JSON.stringify({ username, email, password }),
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
  const project = projects[0] ?? await createProject(userId, '默认学习项目')
  const sessions = await listSessions(project.pid)
  const session = sessions[0] ?? await createSession(project.pid, '新的对话')
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

export async function listDisplayMessages(sid: string): Promise<DisplayMessage[]> {
  const response = await request<MessageListResponse>(`/sessions/${encodeURIComponent(sid)}/messages`)
  return response.messages
    .filter((message) => message.version === 0)
    .map(parseMessage)
    .filter((message): message is DisplayMessage => message !== null)
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
  signal?: AbortSignal,
): Promise<DoneEvent> {
  return streamLoop(sid, { pid, action: 'send', message }, callbacks, signal)
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

// ── 社区技能广场 ────────────────────────────────────────────────────────────────

export type CommunitySort = 'popular' | 'newest'

export interface CommunitySkillSummary {
  id: string
  owner_uuid: string
  name: string
  description: string
  license: string | null
  compatibility: string | null
  size_bytes: number
  downloads: number
  created_at: number
  updated_at: number
}

export interface CommunitySkillDetail extends CommunitySkillSummary {
  body_md: string
}

export interface CommunitySkillListResponse {
  skills: CommunitySkillSummary[]
  total: number
  limit: number
  offset: number
  sort: CommunitySort
}

export interface InstallResponse {
  name: string
  skill_id: string
  downloads: number
}

function nonceHeaders(): Record<string, string> {
  return {
    'X-Nonce': crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    'X-Nonce-Timestamp': String(Date.now() / 1000),
  }
}

export async function listCommunitySkills(params: {
  keyword?: string
  limit?: number
  offset?: number
  sort?: CommunitySort
} = {}): Promise<CommunitySkillListResponse> {
  const search = new URLSearchParams()
  if (params.keyword) search.set('keyword', params.keyword)
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  if (params.offset !== undefined) search.set('offset', String(params.offset))
  search.set('sort', params.sort ?? 'popular')
  return request<CommunitySkillListResponse>(`/community/skills?${search.toString()}`)
}

export async function getCommunitySkill(id: string): Promise<CommunitySkillDetail> {
  return request<CommunitySkillDetail>(`/community/skills/${encodeURIComponent(id)}`)
}

export async function publishCommunitySkill(bodyMd: string): Promise<CommunitySkillDetail> {
  return request<CommunitySkillDetail>('/community/skills', {
    method: 'POST',
    headers: nonceHeaders(),
    body: JSON.stringify({ body_md: bodyMd }),
  })
}

export async function installCommunitySkill(id: string): Promise<InstallResponse> {
  return request<InstallResponse>(`/community/skills/${encodeURIComponent(id)}/install`, {
    method: 'POST',
    headers: nonceHeaders(),
  })
}

export async function deleteCommunitySkill(id: string): Promise<void> {
  await request<void>(`/community/skills/${encodeURIComponent(id)}`, { method: 'DELETE' })
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
