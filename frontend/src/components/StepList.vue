<script setup>
import { ref, watch, nextTick } from 'vue'
import { escapeHtml } from '../composables/useMarkdown.js'

const props = defineProps({
  steps: { type: Array, default: () => [] },
})

const listEl = ref(null)

watch(() => props.steps.length, async () => {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
})
</script>

<template>
  <div class="flex flex-col min-h-0 flex-1">
    <h3 class="text-sm font-semibold mb-1 text-slate-600 shrink-0">⚡ 执行步骤</h3>
    <div
      ref="listEl"
      class="bg-slate-50 border rounded-lg p-3 text-sm space-y-2 flex-1 min-h-0 overflow-y-auto scroll-smooth"
    >
      <span v-if="steps.length === 0" class="text-slate-400 italic">等待开始...</span>
      <div
        v-for="s in steps"
        :key="s.iteration"
        :class="['step-item', s.status]"
      >
        <!-- executing -->
        <template v-if="s.status === 'executing'">
          <div class="font-semibold text-xs text-indigo-700 mb-1">▶ 步骤 {{ s.iteration }}</div>
          <div v-if="s.title" class="text-xs text-slate-600 mb-1">{{ escapeHtml(s.title) }}</div>
          <div class="step-stream text-xs text-slate-500 whitespace-pre-wrap break-words">{{ s.streamContent }}</div>
        </template>
        <!-- done -->
        <template v-else-if="s.status === 'done'">
          <div class="font-semibold text-xs text-emerald-700 mb-1">✓ 步骤 {{ s.iteration }}</div>
          <div v-if="s.title" class="text-xs text-slate-600 mb-1">{{ escapeHtml(s.title) }}</div>
          <div class="text-xs text-slate-500 italic">{{ s.resultPreview }}</div>
        </template>
        <!-- replan -->
        <template v-else-if="s.status === 'replan'">
          <div class="text-xs text-indigo-600">📐 Replanner 调整: 剩余 {{ s.remainingSteps }} 步</div>
        </template>
      </div>
    </div>
  </div>
</template>
