<script setup>
import { ref } from 'vue'

const emit = defineEmits(['upload'])

const dragging = ref(false)
const resultMsg = ref('')
const resultOk = ref(true)
const uploading = ref(false)

const fileInput = ref(null)

function triggerFile() {
  fileInput.value?.click()
}

function onFileChange(e) {
  if (e.target.files[0]) {
    emit('upload', e.target.files[0])
  }
}

function onDragOver(e) {
  e.preventDefault()
  dragging.value = true
}

function onDragLeave() {
  dragging.value = false
}

function onDrop(e) {
  e.preventDefault()
  dragging.value = false
  if (e.dataTransfer.files[0]) {
    emit('upload', e.dataTransfer.files[0])
  }
}

defineExpose({ resultMsg, resultOk, uploading })
</script>

<template>
  <div>
    <h3 class="text-sm font-semibold mb-2 text-slate-600">📤 上传文档</h3>
    <div
      :class="[
        'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition',
        dragging ? 'border-indigo-400 bg-indigo-50' : 'border-slate-300 hover:bg-slate-50',
      ]"
      @click="triggerFile"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <input
        ref="fileInput"
        type="file"
        accept=".md,.markdown,.txt"
        class="hidden"
        @change="onFileChange"
      />
      <div class="text-4xl mb-2">📁</div>
      <div class="text-sm text-slate-600">点击或拖拽 .md/.txt 文件到此</div>
      <div class="text-xs text-slate-400 mt-1">将自动按章节切分并建立向量索引</div>
    </div>
    <div v-if="resultMsg" class="mt-3 text-sm" :class="resultOk ? 'text-emerald-600' : 'text-red-500'">
      {{ resultMsg }}
    </div>
  </div>
</template>
