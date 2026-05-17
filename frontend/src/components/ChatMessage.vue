<script setup>
import { renderMarkdown, escapeHtml } from '../composables/useMarkdown.js'

const props = defineProps({
  role: { type: String, required: true }, // 'user' | 'assistant'
  content: { type: String, default: '' },
})
</script>

<template>
  <div :class="['flex', role === 'user' ? 'justify-end' : 'justify-start']">
    <div :class="['chat-msg', role]">
      <template v-if="role === 'user'">{{ escapeHtml(content) }}</template>
      <template v-else v-html="renderMarkdown(content)"></template>
    </div>
  </div>
</template>
