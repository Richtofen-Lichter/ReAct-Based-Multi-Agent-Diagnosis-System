<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const API = '/api/v1'
const status = ref('checking') // 'checking' | 'ready' | 'partial' | 'down' | 'unreachable'
const healthText = ref('检查中...')
let timer = null

async function checkHealth() {
  try {
    const r = await fetch(`${API}/health/ready`)
    const data = await r.json()
    const ready = data?.data?.status === 'ready'
    const milvusOk = data?.data?.dependencies?.milvus?.status === 'ok'
    const mcpOk = data?.data?.dependencies?.mcp?.status === 'ok'
    if (ready && mcpOk) {
      status.value = 'ready'
      healthText.value = `就绪 · MCP ${data.data.dependencies.mcp.tools_count} 工具`
    } else if (ready) {
      status.value = 'partial'
      healthText.value = '就绪 · MCP 未连'
    } else {
      status.value = 'down'
      healthText.value = 'Milvus 不可用'
    }
  } catch (e) {
    status.value = 'unreachable'
    healthText.value = '服务不可达'
  }
}

onMounted(() => {
  checkHealth()
  timer = setInterval(checkHealth, 15000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="flex items-center space-x-3">
    <span
      class="w-3 h-3 rounded-full"
      :class="{
        'bg-green-400': status === 'ready',
        'bg-yellow-400': status === 'partial' || status === 'checking',
        'bg-red-500': status === 'down' || status === 'unreachable',
      }"
    ></span>
    <span class="text-sm font-mono">{{ healthText }}</span>
  </div>
</template>
