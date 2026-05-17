<script setup>
import { escapeHtml } from '../composables/useMarkdown.js'

defineProps({
  documents: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['refresh', 'delete'])
</script>

<template>
  <div>
    <h3 class="text-sm font-semibold mb-2 text-slate-600 flex items-center justify-between">
      <span>📚 已索引文档</span>
      <button class="text-xs text-indigo-600 hover:underline" @click="emit('refresh')">🔄 刷新</button>
    </h3>
    <div class="space-y-2 max-h-[400px] overflow-y-auto">
      <span v-if="loading" class="text-sm text-slate-400 italic">加载中...</span>
      <span v-else-if="error" class="text-sm text-red-500">{{ error }}</span>
      <span v-else-if="documents.length === 0" class="text-sm text-slate-400 italic">暂无文档, 请先上传</span>
      <div
        v-for="d in documents"
        :key="d.source"
        class="doc-card"
      >
        <div>
          <div class="font-semibold text-sm">{{ escapeHtml(d.source) }}</div>
          <div class="text-xs text-slate-500">{{ d.chunk_count }} 个 chunk</div>
        </div>
        <button
          class="text-red-500 hover:text-red-700 text-sm"
          @click="emit('delete', d.source)"
        >删除</button>
      </div>
    </div>
  </div>
</template>
