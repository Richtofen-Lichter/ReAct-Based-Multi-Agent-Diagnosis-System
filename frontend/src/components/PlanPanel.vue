<script setup>
import { escapeHtml } from '../composables/useMarkdown.js'

defineProps({
  plan: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="shrink-0">
    <h3 class="text-sm font-semibold mb-1 text-slate-600">📋 诊断计划</h3>
    <div class="bg-slate-50 border rounded-lg p-3 text-sm space-y-1 max-h-[160px] overflow-y-auto">
      <span v-if="plan.length === 0" class="text-slate-400 italic">点击"开始诊断"生成计划...</span>
      <div
        v-for="(step, i) in plan"
        :key="i"
        class="flex items-start space-x-2"
      >
        <span class="bg-indigo-100 text-indigo-700 rounded-full w-5 h-5 text-xs flex items-center justify-center flex-shrink-0 mt-0.5">{{ i + 1 }}</span>
        <span class="text-slate-700">{{ escapeHtml(step) }}</span>
      </div>
    </div>
  </div>
</template>
