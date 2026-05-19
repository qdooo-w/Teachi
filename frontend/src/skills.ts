import yaml from 'yaml'
import { type FileEntry, type FileSpace, listFiles, readFile, writeFile, deleteFile, createDirectory } from './api'

export type { FileSpace }

export interface SkillMeta {
  name: string
  description: string
  size: number
  updated_at: number
}

export const SKILL_NAME_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/
export const SKILL_NAME_MAX = 64
export const SKILL_RESERVED = new Set(['anthropic', 'claude'])
export const SKILL_RESOURCE_DIRS = ['references', 'assets'] as const
export const SKILL_TEXT_EXTENSIONS = ['.md', '.txt', '.json', '.yaml', '.yml'] as const

export type SkillResourceDir = typeof SKILL_RESOURCE_DIRS[number]
export type SkillEditorKind = 'skill' | 'markdown' | 'json' | 'yaml' | 'text'

export interface SkillTreeEntry {
  name: string
  relPath: string
  isDir: boolean
  virtual: boolean
  parent: '' | SkillResourceDir
  size: number
  updated_at: number
}

export function validateSkillName(name: string): string | null {
  if (!name) return '名称不能为空'
  if (name.length > SKILL_NAME_MAX) return `名称不能超过 ${SKILL_NAME_MAX} 个字符`
  if (!SKILL_NAME_PATTERN.test(name)) return '名称只能包含小写字母、数字和连字符，且不能以连字符开头或结尾'
  for (const reserved of SKILL_RESERVED) {
    if (name.includes(reserved)) return `名称不能包含保留词 "${reserved}"`
  }
  return null
}

function normalizeParts(path: string): string[] {
  return path.split('/').filter(Boolean)
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot >= 0 ? filename.slice(dot).toLowerCase() : ''
}

function isAllowedTextFile(filename: string): boolean {
  return (SKILL_TEXT_EXTENSIONS as readonly string[]).includes(extensionOf(filename))
}

function isResourceDir(value: string): value is SkillResourceDir {
  return (SKILL_RESOURCE_DIRS as readonly string[]).includes(value)
}

export function validateSkillRelativePath(path: string, allowDirectory = false): string | null {
  if (!path.trim()) return '路径不能为空'
  if (path.includes('\0')) return '路径不能包含 NUL 字符'
  if (path.startsWith('/') || path.startsWith('\\')) return '路径必须是相对路径'

  const parts = normalizeParts(path.replace(/\\/g, '/'))
  if (parts.length === 0) return '路径不能为空'
  if (parts.some((part) => part === '.' || part === '..')) return '路径不能包含 . 或 ..'
  if (parts.length === 1 && parts[0] === 'SKILL.md') return null

  if (parts.length === 1) {
    const [name] = parts
    if (allowDirectory && isResourceDir(name)) return null
    if (!isAllowedTextFile(name)) return '只允许 md、txt、json、yaml、yml 文本文件'
    return null
  }

  if (parts.length === 2) {
    const [folder, filename] = parts
    if (!isResourceDir(folder)) return '只能使用 references 或 assets 文件夹'
    if (!isAllowedTextFile(filename)) return '只允许 md、txt、json、yaml、yml 文本文件'
    return null
  }

  return '暂不支持嵌套目录'
}

export function skillFileEditorKind(relPath: string): SkillEditorKind {
  if (relPath === 'SKILL.md') return 'skill'
  const ext = extensionOf(relPath)
  if (ext === '.md') return 'markdown'
  if (ext === '.json') return 'json'
  if (ext === '.yaml' || ext === '.yml') return 'yaml'
  return 'text'
}

export function validatePlainSkillFileContent(relPath: string, content: string): string | null {
  const kind = skillFileEditorKind(relPath)
  if (kind === 'markdown') {
    if (!content.startsWith('---')) return null
    const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/)
    if (!match) return 'Markdown frontmatter 未闭合。'
    try {
      yaml.parse(match[1])
    } catch (e) {
      return `Markdown frontmatter YAML 语法错误：${(e as Error).message}`
    }
    return null
  }
  if (kind === 'json') {
    try {
      JSON.parse(content)
    } catch (e) {
      return `JSON 语法错误：${(e as Error).message}`
    }
    return null
  }
  if (kind === 'yaml') {
    try {
      yaml.parse(content)
    } catch (e) {
      return `YAML 语法错误：${(e as Error).message}`
    }
  }
  return null
}

export function initialSkillFileContent(filename: string): string {
  const kind = skillFileEditorKind(filename)
  if (kind === 'json') return '{}\n'
  return ''
}

export interface FrontmatterResult {
  ok: boolean
  error?: string
  name?: string
  description?: string
  raw?: Record<string, unknown>
}

/**
 * 严格解析 SKILL.md frontmatter，返回结构化结果。
 * - 必须有 `---\n...\n---` 块
 * - YAML 必须解析为对象（不能是 str/null/array），否则 pydantic_ai_skills 会在 .get() 上崩溃
 * - 必须包含非空 `name` 和 `description`
 */
export function parseSkillFrontmatter(content: string): FrontmatterResult {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!match) {
    return { ok: false, error: '缺少 frontmatter 块：文件必须以 `---` 开头并以 `---` 结尾包裹 YAML。' }
  }

  let raw: unknown
  try {
    raw = yaml.parse(match[1])
  } catch (e) {
    return { ok: false, error: `YAML 语法错误：${(e as Error).message}` }
  }

  if (raw === null || raw === undefined) {
    return { ok: false, error: 'frontmatter 为空。' }
  }

  if (typeof raw !== 'object' || Array.isArray(raw)) {
    // 最常见 bug：`name:foo` 漏空格，被当作单个字符串
    return {
      ok: false,
      error: 'frontmatter 必须是键值对形式。常见原因：冒号后漏了空格（正确写法是 `name: foo`，错误写法是 `name:foo`）。',
    }
  }

  const obj = raw as Record<string, unknown>

  if (typeof obj.name !== 'string' || !obj.name.trim()) {
    return { ok: false, error: 'frontmatter 必须包含非空字符串字段 `name`。' }
  }

  if (typeof obj.description !== 'string' || !obj.description.trim()) {
    return { ok: false, error: 'frontmatter 必须包含非空字符串字段 `description`。' }
  }

  return {
    ok: true,
    name: obj.name.trim(),
    description: obj.description.trim(),
    raw: obj,
  }
}

export async function listSkills(space: FileSpace): Promise<SkillMeta[]> {
  let entries
  try {
    entries = await listFiles(space, 'skills')
  } catch {
    return []
  }

  const dirs = entries.filter((e) => e.is_dir)

  const results = await Promise.all(
    dirs.map(async (dir) => {
      try {
        const file = await readFile(space, `skills/${dir.name}/SKILL.md`)
        const fm = parseSkillFrontmatter(file.content)
        return {
          name: dir.name,
          description: fm?.description ?? '',
          size: file.size,
          updated_at: file.updated_at,
        } satisfies SkillMeta
      } catch {
        return null
      }
    }),
  )

  return results
    .filter((s): s is SkillMeta => s !== null)
    .sort((a, b) => b.updated_at - a.updated_at)
}

export async function readSkill(space: FileSpace, name: string): Promise<{ content: string }> {
  const file = await readFile(space, `skills/${name}/SKILL.md`)
  return { content: file.content }
}

export async function writeSkill(space: FileSpace, name: string, content: string): Promise<void> {
  await writeFile(space, `skills/${name}/SKILL.md`, content)
}

export async function deleteSkill(space: FileSpace, name: string): Promise<void> {
  await deleteFile(space, `skills/${name}`)
}

export function buildSkillTemplate(name: string): string {
  return `---\nname: ${name}\ndescription: \n---\n\n# 技能说明\n\n`
}

function toTreeFile(entry: FileEntry, parent: '' | SkillResourceDir): SkillTreeEntry | null {
  if (entry.is_dir || validateSkillRelativePath(parent ? `${parent}/${entry.name}` : entry.name) !== null) {
    return null
  }
  return {
    name: entry.name,
    relPath: parent ? `${parent}/${entry.name}` : entry.name,
    isDir: false,
    virtual: false,
    parent,
    size: entry.size,
    updated_at: entry.updated_at,
  }
}

export async function listSkillTree(space: FileSpace, name: string): Promise<SkillTreeEntry[]> {
  const nameError = validateSkillName(name)
  if (nameError) throw new Error(nameError)

  const rootEntries = await listFiles(space, `skills/${name}`)
  const rootFiles = rootEntries
    .map((entry) => toTreeFile(entry, ''))
    .filter((entry): entry is SkillTreeEntry => entry !== null)
    .sort((a, b) => {
      if (a.name === 'SKILL.md') return -1
      if (b.name === 'SKILL.md') return 1
      return a.name.localeCompare(b.name)
    })

  const tree: SkillTreeEntry[] = [...rootFiles]
  const rootDirNames = new Set(rootEntries.filter((entry) => entry.is_dir).map((entry) => entry.name))

  for (const dir of SKILL_RESOURCE_DIRS) {
    const isVirtual = !rootDirNames.has(dir)
    tree.push({
      name: dir,
      relPath: dir,
      isDir: true,
      virtual: isVirtual,
      parent: '',
      size: 0,
      updated_at: 0,
    })

    if (!isVirtual) {
      let children: FileEntry[] = []
      try {
        children = await listFiles(space, `skills/${name}/${dir}`)
      } catch {
        children = []
      }
      tree.push(
        ...children
          .map((entry) => toTreeFile(entry, dir))
          .filter((entry): entry is SkillTreeEntry => entry !== null)
          .sort((a, b) => a.name.localeCompare(b.name)),
      )
    }
  }

  return tree
}

export async function readSkillFile(
  space: FileSpace,
  name: string,
  relPath: string,
): Promise<{ content: string; size: number; updated_at: number }> {
  const pathError = validateSkillRelativePath(relPath)
  if (pathError) throw new Error(pathError)
  const file = await readFile(space, `skills/${name}/${relPath}`)
  return { content: file.content, size: file.size, updated_at: file.updated_at }
}

export async function writeSkillFile(
  space: FileSpace,
  name: string,
  relPath: string,
  content: string,
): Promise<void> {
  const pathError = validateSkillRelativePath(relPath)
  if (pathError) throw new Error(pathError)
  const contentError = validatePlainSkillFileContent(relPath, content)
  if (contentError) throw new Error(contentError)
  await writeFile(space, `skills/${name}/${relPath}`, content)
}

export async function createSkillFile(
  space: FileSpace,
  name: string,
  relPath: string,
): Promise<void> {
  await writeSkillFile(space, name, relPath, initialSkillFileContent(relPath))
}

export async function deleteSkillFile(space: FileSpace, name: string, relPath: string): Promise<void> {
  if (relPath === 'SKILL.md') throw new Error('不能删除 SKILL.md，请删除整个技能。')
  const pathError = validateSkillRelativePath(relPath, true)
  if (pathError) throw new Error(pathError)
  await deleteFile(space, `skills/${name}/${relPath}`)
}

export async function createSkillDirectory(space: FileSpace, name: string, dir: SkillResourceDir): Promise<void> {
  await createDirectory(space, `skills/${name}/${dir}`)
}

// ── 项目简介 skill ────────────────────────────────────────────────────────────

export const PROJECT_DESC_SKILL = 'project-description'

/**
 * 生成项目简介 skill 文件内容。
 * @param summary  frontmatter description 的可变部分（可为空）
 * @param body     正文简介（可为空）
 */
export function buildProjectDescSkill(summary: string, body: string): string {
  const description = summary.trim()
    ? `项目简介：${summary.trim()}`
    : '项目简介'
  return buildSkillFile({ name: PROJECT_DESC_SKILL, description, body: body.trim() })
}

// ── 结构化 skill 文件 ─────────────────────────────────────────────────────────

export interface SkillFields {
  name: string
  description: string
  license?: string
  compatibility?: string
  body: string
}

export interface ParseSkillFileResult {
  ok: boolean
  error?: string
  fields?: SkillFields
}

/**
 * 把 SKILL.md 拆成结构化字段。
 * 对 frontmatter 做严格校验（必须是对象 + 有 name/description），
 * 把 --- 之后的所有内容当成 body。
 */
export function parseSkillFile(content: string): ParseSkillFileResult {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/)
  if (!match) {
    return { ok: false, error: '缺少 frontmatter 块。' }
  }

  const fm = parseSkillFrontmatter(content)
  if (!fm.ok) {
    return { ok: false, error: fm.error }
  }

  const raw = fm.raw as Record<string, unknown>
  return {
    ok: true,
    fields: {
      name: fm.name!,
      description: fm.description!,
      license: typeof raw.license === 'string' ? raw.license : undefined,
      compatibility: typeof raw.compatibility === 'string' ? raw.compatibility : undefined,
      body: match[2] ?? '',
    },
  }
}

/**
 * 由结构化字段生成合法的 SKILL.md 文本。
 * 用 yaml.stringify 生成 frontmatter，保证语法正确。
 */
export function buildSkillFile(fields: SkillFields): string {
  const meta: Record<string, string> = {
    name: fields.name,
    description: fields.description,
  }
  if (fields.license && fields.license.trim()) meta.license = fields.license.trim()
  if (fields.compatibility && fields.compatibility.trim()) meta.compatibility = fields.compatibility.trim()

  // yaml.stringify 默认会在末尾加 \n
  const fm = yaml.stringify(meta).trimEnd()
  const body = fields.body.replace(/^\s+/, '') // 去掉开头多余空行
  return `---\n${fm}\n---\n\n${body}`
}
