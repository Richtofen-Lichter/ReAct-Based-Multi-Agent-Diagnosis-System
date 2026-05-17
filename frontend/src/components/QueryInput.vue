<script setup>
const props = defineProps({
  modelValue: { type: String, default: '' },
  running: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'start', 'stop'])
</script>

<template>
  <div>
    <label class="block text-sm font-semibold mb-2">告警内容 / 故障描述</label>
    <textarea
      :value="modelValue"
      @input="emit('update:modelValue', $event.target.value)"
      rows="3"
      class="w-full p-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-400 text-sm font-mono"
      placeholder="例如: 我的电脑内存占用居高不下, 系统开始卡顿..."
    >我的电脑内存占用居高不下, 系统明显卡顿, 浏览器和开发工具响应变慢, 已持续 12 分钟</textarea>
  </div>
  <div class="flex space-x-2">
    <button
      :disabled="running"
      @click="emit('start')"
      class="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2 rounded-lg transition"
    >🚀 开始诊断</button>
    <button
      :disabled="!running"
      @click="emit('stop')"
      class="px-4 bg-slate-200 hover:bg-slate-300 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm"
    >停止</button>
  </div>
</template>
