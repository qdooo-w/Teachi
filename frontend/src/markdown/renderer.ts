import MarkdownIt from 'markdown-it'
import texmath from 'markdown-it-texmath'
import katex from 'katex'
import DOMPurify from 'dompurify'

import { highlightCode, getLanguageLabel } from './highlight'

/**
 * 单例 markdown-it：
 * - html:false 禁止原始 HTML 穿透
 * - linkify:true 自动识别 URL
 * - fence 自定义渲染：mermaid 保留为占位代码块；其它语言交给 highlight.js
 * - 链接强制 target="_blank" + rel=noopener,noreferrer,nofollow
 * - 数学公式交由 markdown-it-texmath + KaTeX 直接渲染为 HTML
 */
const md: MarkdownIt = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
  typographer: false,
})

md.use(texmath, {
  engine: katex,
  delimiters: ['dollars', 'brackets'],
  katexOptions: {
    throwOnError: false,
    strict: 'ignore',
    output: 'html',
  },
})

const defaultLinkOpen =
  md.renderer.rules.link_open ??
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const targetIdx = token.attrIndex('target')
  if (targetIdx < 0) token.attrPush(['target', '_blank'])
  else token.attrs![targetIdx][1] = '_blank'
  const relIdx = token.attrIndex('rel')
  const relValue = 'noopener noreferrer nofollow'
  if (relIdx < 0) token.attrPush(['rel', relValue])
  else token.attrs![relIdx][1] = relValue
  return defaultLinkOpen(tokens, idx, options, env, self)
}

md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const raw = token.content
  const info = (token.info || '').trim()
  const lang = info.split(/\s+/)[0] || ''
  const langLabel = getLanguageLabel(lang)

  if (lang.toLowerCase() === 'mermaid') {
    return (
      `<pre data-lang="mermaid" class="mermaid-source" data-source="${attr(raw)}">` +
      `<code>${escapeHtml(raw)}</code>` +
      `</pre>`
    )
  }

  const highlighted = highlightCode(raw, lang)
  return (
    `<div class="code-block" data-lang="${attr(langLabel)}">` +
    `<div class="code-block-header">` +
    `<span class="code-block-lang">${escapeHtml(langLabel)}</span>` +
    `<button type="button" class="code-copy-btn" data-copy>复制</button>` +
    `</div>` +
    `<pre class="hljs"><code class="language-${attr(langLabel)}">${highlighted}</code></pre>` +
    `</div>`
  )
}

/**
 * DOMPurify 放行：
 * - USE_PROFILES 打开 html/svg/mathml，供 KaTeX 与 Mermaid 输出使用
 * - ADD_TAGS 补上 markdown-it-texmath 的 <eq>/<eqn>/<section>
 * - ADD_ATTR 放行 data-* 与链接属性
 */
const PURIFY_OPTIONS = {
  USE_PROFILES: { html: true, svg: true, mathMl: true },
  ADD_TAGS: ['eq', 'eqn', 'section', 'foreignObject'],
  ADD_ATTR: [
    'data-lang',
    'data-source',
    'data-math',
    'data-rendered',
    'data-copy',
    'data-copy-mounted',
    'target',
    'rel',
  ],
} as const

export function renderMarkdown(src: string): string {
  const html = md.render(src || '')
  return DOMPurify.sanitize(html, PURIFY_OPTIONS as unknown as Record<string, unknown>) as string
}

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function attr(value: string): string {
  return escapeHtml(value)
}
