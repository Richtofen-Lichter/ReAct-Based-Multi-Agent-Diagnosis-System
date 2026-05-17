<script setup>
defineProps({
  reportHtml: { type: String, default: '' },
})
</script>

<template>
  <div
    class="prose prose-sm max-w-none border rounded-lg p-5 bg-white flex-1 min-h-0 overflow-y-auto"
    v-html="reportHtml"
  ></div>
</template>
