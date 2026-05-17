<script setup>
import { escapeHtml } from '../composables/useMarkdown.js'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  completed: { type: Boolean, default: false },
  failed: { type: Boolean, default: false },
})

function iconForStage(stage) {
  switch (stage) {
    case 'rewrite':      return '✏️'
    case 'rewrite_done': return '✅'
    case 'retrieve':     return '🔍'
    case 'retrieve_done':return '📚'
    case 'web':          return '🌐'
    case 'web_done':     return '🌐'
    case 'llm_start':    return '🤖'
    case 'tool_call':    return '🛠️'
    case 'stats':        return '📊'
    default:             return '•'
  }
}

function renderDetails(stage, data) {
  if (!data || typeof data !== 'object') return ''
  if (stage === 'rewrite_done') {
    const orig = data.original || ''
    const rew = data.rewritten || ''
    if (!orig && !rew) return ''
    return `<div><span class="text-slate-400">原始:</span> ${escapeHtml(orig)}</div><div><span class="text-slate-400">改写:</span> ${escapeHtml(rew)}</div>`
  }
  if (stage === 'retrieve_done') {
    const hits = Array.isArray(data.hits) ? data.hits : []
    if (!hits.length) return '<div class="text-slate-400">无命中片段</div>'
    const meta = `<div class="text-slate-400 mb-1">top_k=${data.top_k ?? '?'} · ${escapeHtml(data.mode || '')}</div>`
    const items = hits.map((h, i) => {
      const score = (h.score !== null && h.score !== undefined) ? `<span class="text-emerald-600">score ${h.score}</span>` : ''
      const chap = h.chapter ? ` · 章节: ${escapeHtml(h.chapter)}` : ''
      return `<div class="border-l-2 border-indigo-200 pl-2"><div class="font-medium text-slate-700">${i + 1}. ${escapeHtml(h.source || '未知')} ${score}${chap}</div><div class="text-slate-500">${escapeHtml(h.preview || '')}</div></div>`
    }).join('')
    return meta + items
  }
  if (stage === 'web_done') {
    const results = Array.isArray(data.results) ? data.results : []
    if (!results.length) {
      return `<div class="text-slate-400">${escapeHtml(data.skip_reason || '未触发联网')}</div>`
    }
    const meta = data.provider ? `<div class="text-slate-400 mb-1">provider=${escapeHtml(data.provider)}</div>` : ''
    const items = results.map((r, i) => {
      const url = r.url || ''
      const titleEsc = escapeHtml(r.title || '(无标题)')
      const titleHtml = url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener" class="text-indigo-600 hover:underline">${titleEsc}</a>` : titleEsc
      return `<div class="border-l-2 border-emerald-200 pl-2"><div class="font-medium">${i + 1}. ${titleHtml}</div>${url ? `<div class="text-[10px] text-slate-400 break-all">${escapeHtml(url)}</div>` : ''}<div class="text-slate-500">${escapeHtml(r.snippet || '')}</div></div>`
    }).join('')
    return meta + items
  }
  if (stage === 'stats') {
    return `<div>模型: <span class="font-medium">${escapeHtml(data.model || '?')}</span></div><div>输入 tokens: <span class="font-medium">${data.input_tokens ?? 0}</span></div><div>输出 tokens: <span class="font-medium">${data.output_tokens ?? 0}</span></div><div>合计 tokens: <span class="font-medium">${data.total_tokens ?? 0}</span></div><div>生成耗时: <span class="font-medium">${data.llm_ms ?? 0} ms</span></div><div>总耗时: <span class="font-medium">${data.total_ms ?? 0} ms</span></div><div>回答字数: <span class="font-medium">${data.answer_chars ?? 0}</span></div>${data.tools_enabled ? '<div class="text-emerald-600">工具回合: 已启用</div>' : ''}`
  }
  if (stage === 'llm_start') {
    const tools = Array.isArray(data.tools) ? data.tools : []
    if (data.tools_enabled && tools.length) {
      const chips = tools.map(name => `<span class="inline-block px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-100 mr-1 mb-1 font-mono text-[10px]">${escapeHtml(name)}</span>`).join('')
      return `<div class="text-slate-500 mb-1">模型: <span class="font-medium">${escapeHtml(data.model || '?')}</span></div><div class="text-slate-500 mb-1">已为模型启用 ${tools.length} 个只读工具, 模型可按需自主调用:</div><div class="flex flex-wrap">${chips}</div>`
    }
    return `<div class="text-slate-500">模型: <span class="font-medium">${escapeHtml(data.model || '?')}</span> · 工具回合: 未启用</div>`
  }
  if (stage === 'tool_call') {
    const ok = (data.status || '').toLowerCase() === 'ok'
    return `<div>工具: <span class="font-mono text-slate-700">${escapeHtml(data.name || '?')}</span></div><div>状态: <span class="${ok ? 'text-emerald-600' : 'text-rose-600'} font-medium">${ok ? '✓' : '✗'} ${escapeHtml(data.status || '?')}</span></div><div>耗时: <span class="font-medium">${data.elapsed_ms ?? 0} ms</span></div><div>输出: <span class="font-medium">${data.result_chars ?? 0} 字符</span></div>${data.read_only === false ? '<div class="text-amber-600">⚠ 非只读工具</div>' : ''}`
  }
  return ''
}
</script>

<template>
  <div class="flex justify-start">
    <div class="rag-progress bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2 text-xs text-slate-600 space-y-1 max-w-[85%]">
      <div class="rag-progress-head font-medium text-indigo-700 flex items-center gap-2">
        <template v-if="failed">
          <span class="text-red-500">✗ 检索流程中断</span>
        </template>
        <template v-else-if="completed">
          <span class="text-emerald-600">✓ 检索流程完成</span>
        </template>
        <template v-else>
          <span class="rag-spinner inline-block w-2 h-2 rounded-full bg-indigo-400 animate-pulse"></span>
          <span>正在检索并生成回答…</span>
        </template>
      </div>
      <div class="rag-progress-rows space-y-0.5">
        <div
          v-for="(row, i) in rows"
          :key="i"
          class="rag-progress-row"
        >
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="shrink-0">{{ iconForStage(row.stage) }}</span>
            <span class="text-slate-700 font-medium">{{ escapeHtml(row.label || row.stage || '') }}</span>
            <span v-if="row.detail" class="text-slate-400 truncate">{{ escapeHtml(row.detail) }}</span>
            <span v-if="row.elapsed" class="ml-1 text-[10px] text-indigo-500">{{ row.elapsed }}ms</span>
          </div>
          <div
            v-if="renderDetails(row.stage, row.data)"
            class="rag-details mt-1 ml-5 text-[11px] text-slate-600 bg-white border border-indigo-100 rounded p-2 space-y-1"
            v-html="renderDetails(row.stage, row.data)"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>
