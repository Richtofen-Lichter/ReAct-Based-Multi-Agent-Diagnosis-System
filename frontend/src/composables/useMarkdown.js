export function escapeHtml(s) {
  if (s == null) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 极简 Markdown → HTML (够用即可, 不引第三方库)
 */
export function renderMarkdown(md) {
  if (!md) return ''
  // 处理 LLM 偶尔输出 \n 字面量
  let s = String(md).replace(/\\n/g, '\n').replace(/\\t/g, '\t')
  let h = escapeHtml(s)
  // 代码块
  h = h.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code}</code></pre>`)
  // 行内代码
  h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>')
  // 标题
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  h = h.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  // 加粗
  h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  // 列表
  h = h.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>')
  h = h.replace(/(<li>[\s\S]*?<\/li>)(\n<li>)/g, '$1$2')
  h = h.replace(/(<li>[\s\S]+?<\/li>)/g, (m) => `<ul>${m}</ul>`)
  h = h.replace(/<\/ul>\s*<ul>/g, '')
  // 段落
  h = h.replace(/\n\n/g, '</p><p>')
  h = h.replace(/\n/g, '<br>')
  return `<p>${h}</p>`
}
