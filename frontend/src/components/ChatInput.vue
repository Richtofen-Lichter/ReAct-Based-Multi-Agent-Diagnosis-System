<script setup>
import { ref } from 'vue'

const props = defineProps({
  webEnabled: { type: Boolean, default: false },
  mcpEnabled: { type: Boolean, default: true },
})

const emit = defineEmits(['send', 'toggleWeb', 'toggleMcp'])

const input = ref('')
</script>

<template>
  <div>
    <div class="flex items-center space-x-2">
      <input
        v-model="input"
        type="text"
        class="flex-1 p-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm"
        placeholder="例如: 我的电脑内存占用居高不下"
        @keydown.enter.prevent="emit('send', input); input = ''"
      />
      <button
        type="button"
        :title="webEnabled ? '已启用联网搜索' : '启用后会把外网搜索结果作为回答的补充资料'"
        :class="[
          'px-3 py-2 rounded-lg border text-xs font-medium select-none transition',
          webEnabled
            ? 'border-emerald-400 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
            : 'border-slate-300 text-slate-500 hover:bg-slate-100',
        ]"
        @click="emit('toggleWeb')"
      >🌐 联网 <span>{{ webEnabled ? '开' : '关' }}</span></button>
      <button
        type="button"
        :title="mcpEnabled ? '已启用 MCP 工具' : '启用后允许 RAG Chat 调用 MCP 只读工具查询本机/容器/网络状态'"
        :class="[
          'px-3 py-2 rounded-lg border text-xs font-medium select-none transition',
          mcpEnabled
            ? 'border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100'
            : 'border-slate-300 text-slate-500 hover:bg-slate-100',
        ]"
        @click="emit('toggleMcp')"
      >🛠 MCP <span>{{ mcpEnabled ? '开' : '关' }}</span></button>
      <button
        class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 rounded-lg font-semibold"
        @click="emit('send', input); input = ''"
      >发送</button>
    </div>
    <div class="text-[11px] text-slate-400 mt-1">联网会调用第三方搜索 API (默认 Tavily), 无 API Key 时返回 mock 数据.</div>
  </div>
</template>
