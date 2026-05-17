<script setup>
import { escapeHtml } from '../composables/useMarkdown.js'

defineProps({
  monitor: { type: Object, required: true },
})
</script>

<template>
  <div class="flex flex-col flex-1 min-h-0 border rounded-lg bg-white p-4 space-y-3 overflow-hidden">
    <!-- 指标卡 -->
    <div class="grid grid-cols-4 gap-3 shrink-0">
      <div class="bg-indigo-50 border border-indigo-100 rounded-lg p-3">
        <div class="text-[10px] uppercase tracking-wider text-indigo-500">当前步骤</div>
        <div class="text-xl font-semibold text-indigo-700 mt-0.5">{{ monitor.step }}</div>
        <div class="text-[11px] text-indigo-400 truncate">{{ monitor.stepLabel }}</div>
      </div>
      <div class="bg-emerald-50 border border-emerald-100 rounded-lg p-3">
        <div class="text-[10px] uppercase tracking-wider text-emerald-600">耗时</div>
        <div class="text-xl font-semibold text-emerald-700 mt-0.5">{{ monitor.elapsed }}s</div>
        <div class="text-[11px] text-emerald-500">自诊断开始</div>
      </div>
      <div class="bg-amber-50 border border-amber-100 rounded-lg p-3">
        <div class="text-[10px] uppercase tracking-wider text-amber-600">工具调用</div>
        <div class="text-xl font-semibold text-amber-700 mt-0.5">{{ monitor.toolCount }}</div>
        <div class="text-[11px] text-amber-500">失败 {{ monitor.toolFail }}</div>
      </div>
      <div class="bg-slate-100 border border-slate-200 rounded-lg p-3">
        <div class="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
          <span>{{ monitor.hasRealUsage ? '真实 Tokens' : '真实 Tokens' }}</span>
          <span class="text-[9px] text-slate-400 normal-case font-normal">{{ monitor.hasRealUsage ? 'API 实测' : '~估算' }}</span>
        </div>
        <div class="text-xl font-semibold text-slate-700 mt-0.5">{{ monitor.tokens }}</div>
        <div class="text-[11px] text-slate-500 truncate" :title="monitor.tokensTooltip">{{ monitor.tokensDetail }}</div>
      </div>
    </div>

    <!-- 两栏: 左 实时输出, 右 工具流水 -->
    <div class="grid grid-cols-5 gap-3 flex-1 min-h-0">
      <div class="col-span-3 flex flex-col min-h-0 border rounded-lg bg-slate-50">
        <div class="px-3 py-2 text-xs font-semibold text-slate-600 border-b bg-white rounded-t-lg shrink-0 flex justify-between">
          <span>🧠 Executor 实时输出</span>
          <span class="text-slate-400 font-normal">{{ monitor.streamHint }}</span>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto p-3 text-xs text-slate-700 whitespace-pre-wrap break-words font-mono leading-relaxed">
          <span v-if="!monitor.streamContent" class="text-slate-400 italic">诊断开始后, 模型生成的文本会实时显示在此...</span>
          <template v-else>{{ monitor.streamContent }}</template>
        </div>
      </div>
      <div class="col-span-2 flex flex-col min-h-0 border rounded-lg bg-slate-50">
        <div class="px-3 py-2 text-xs font-semibold text-slate-600 border-b bg-white rounded-t-lg shrink-0">
          🛠️ 工具调用流水
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto p-2 space-y-1 text-xs">
          <span v-if="monitor.toolFeed.length === 0" class="text-slate-400 italic px-2">暂无工具调用</span>
          <div
            v-for="(t, i) in monitor.toolFeed"
            :key="i"
            class="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-50 border-b border-slate-100"
          >
            <span :class="[t.ok ? 'text-emerald-600' : 'text-rose-600', 'font-semibold']">{{ t.ok ? '✓' : '✗' }}</span>
            <span class="font-mono text-slate-700 truncate">{{ escapeHtml(t.name) }}</span>
            <span class="text-slate-400 ml-auto shrink-0">{{ escapeHtml(t.elapsed) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
