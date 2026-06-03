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

/**
 * texmath 默认不在 <eq>/<eqn> 上携带原始公式，需注入 data-math 属性，
 * 供 MessageContent.vue 中的 attachMathCopyButtons 读取并复制 LaTeX 源码。
 *
 * 注入策略：包装 texmath 注册的每条渲染规则，调用原规则获取 HTML 字符串后，
 * 向第一个 <eq> 或 <eqn> 开标签注入 data-math="<转义后的原始公式>"。
 * 规则名称（来自 texmath.js 源码）：
 *   内联：math_inline（→ <eq>）、math_inline_double（→ <section><eqn>）
 *   块级：math_block（→ <section><eqn>）、math_block_eqno（→ <section class="eqno"><eqn>）
 */
const MATH_RULE_NAMES = ['math_inline', 'math_inline_double', 'math_block', 'math_block_eqno'] as const

for (const ruleName of MATH_RULE_NAMES) {
  const originalRule = md.renderer.rules[ruleName]
  if (!originalRule) continue

  md.renderer.rules[ruleName] = (tokens, idx, options, env, self) => {
    const html = originalRule(tokens, idx, options, env, self)
    const rawLatex = tokens[idx].content
    const escapedLatex = attr(rawLatex)
    // 向首个 <eq> 或 <eqn> 开标签注入 data-math 属性。
    // math_inline 规则输出以 <eq> 开头；
    // math_inline_double / math_block / math_block_eqno 输出以 <section> 开头，
    // 内部首个 <eqn> 才是公式容器，因此用非锚定匹配查找第一个 <eq> 或 <eqn>。
    return html.replace(/(<(?:eq|eqn)(?:\s[^>]*)?)>/, `$1 data-math="${escapedLatex}">`)
  }
}

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

function preprocessMathPipes(src: string): string {
  if (!src) return ''

  const placeholders: string[] = []
  let processed = src

  // 1. Extract block code (```...```) to protect its content
  processed = processed.replace(/(```[\s\S]*?```)/g, (match) => {
    placeholders.push(match)
    return `__CODE_BLOCK_PLACEHOLDER_${placeholders.length - 1}__`
  })

  // 2. Extract inline code (`...`) to protect its content
  processed = processed.replace(/(`[^`\n]*?`)/g, (match) => {
    placeholders.push(match)
    return `__CODE_BLOCK_PLACEHOLDER_${placeholders.length - 1}__`
  })

  // 3. Replace pipes inside math blocks ($...$ and $$...$$) with LaTeX macros
  const mathRegex = /(\$\$(?:\\[\s\S]|[^\\])+?\$\$)|(\$(?:\\[^\n]|[^\$\n\\])+\$)/g
  processed = processed.replace(mathRegex, (match) => {
    let mathContent = match
    // Replace double escaped pipes/norm macros with \Vert{}
    mathContent = mathContent.replace(/\\\|/g, '\\Vert{}')
    // Replace single pipes with \vert{}
    mathContent = mathContent.replace(/\|/g, '\\vert{}')
    return mathContent
  })

  // 4. Restore extracted code blocks
  for (let i = placeholders.length - 1; i >= 0; i--) {
    processed = processed.replace(`__CODE_BLOCK_PLACEHOLDER_${i}__`, placeholders[i])
  }

  return processed
}

export function renderMarkdown(src: string): string {
  const preprocessed = preprocessMathPipes(src || '')
  const html = md.render(preprocessed)
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
