<script setup>
import { ref } from 'vue'

const props = defineProps({
  content: { type: String, default: '' },
})

const collapsed = ref(false)
</script>

<template>
  <div class="flex justify-start">
    <div class="rag-thinking bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-500 max-w-[85%] space-y-1">
      <div class="rag-thinking-head flex items-center gap-1.5 cursor-pointer select-none" @click="collapsed = !collapsed">
        <span>🧠</span>
        <span class="font-medium text-slate-600">思考过程</span>
        <span class="ml-auto text-[10px] text-slate-400">{{ collapsed ? '▶ 展开' : '▼ 收起' }}</span>
      </div>
      <pre
        :class="['rag-thinking-content whitespace-pre-wrap font-sans text-[11px] leading-relaxed text-slate-500 max-h-48 overflow-auto', { hidden: collapsed }]"
      >{{ content }}</pre>
    </div>
  </div>
</template>
