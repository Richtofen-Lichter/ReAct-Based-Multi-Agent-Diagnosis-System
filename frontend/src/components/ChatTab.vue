<script setup>
import { ref, nextTick } from 'vue'
import { consumeSSE } from '../composables/useSSE.js'
import { renderMarkdown, escapeHtml } from '../composables/useMarkdown.js'
import ChatMessage from './ChatMessage.vue'
import ThinkingBubble from './ThinkingBubble.vue'
import ProgressBubble from './ProgressBubble.vue'
import ChatInput from './ChatInput.vue'

const API = '/api/v1'

const messages = ref([])       // { type: 'msg', role, content }  |  { type: 'thinking', content }  |  { type: 'progress', rows, completed, failed }
const chatWebEnabled = ref(false)
const chatMcpEnabled = ref(true)
const sending = ref(false)

const msgContainer = ref(null)

async function scrollToBottom() {
  await nextTick()
  if (msgContainer.value) {
    msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  }
}

function send(question) {
  if (!question || !question.trim()) return
  sendChat(question.trim())
}

async function sendChat(question) {
  // Add user message
  messages.value.push({ type: 'msg', role: 'user', content: question })
  await scrollToBottom()

  // Add progress placeholder
  const progressMsg = { type: 'progress', rows: [], completed: false, failed: false }
  messages.value.push(progressMsg)

  // Add thinking placeholder (hidden until content arrives)
  const thinkingMsg = { type: 'thinking', content: '', visible: false }
  messages.value.push(thinkingMsg)

  // Add assistant placeholder
  const assistantMsg = { type: 'msg', role: 'assistant', content: '', visible: false }
  messages.value.push(assistantMsg)

  sending.value = true

  try {
    const resp = await fetch(`${API}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: 'web-chat',
        question,
        top_k: 3,
        web_search: chatWebEnabled.value,
        mcp_tools: chatMcpEnabled.value,
      }),
    })

    let tokenBuf = ''
    let tokenStarted = false
    let thinkingStarted = false

    await consumeSSE(resp, (ev) => {
      if (ev.type === 'progress') {
        progressMsg.rows.push({
          stage: ev.stage,
          label: ev.label,
          detail: ev.detail,
          elapsed: ev.elapsed_ms,
          data: ev.data,
        })
        scrollToBottom()
      } else if (ev.type === 'thinking') {
        if (!thinkingStarted) {
          thinkingStarted = true
          thinkingMsg.visible = true
        }
        thinkingMsg.content = (thinkingMsg.content || '') + (ev.content || '')
        scrollToBottom()
      } else if (ev.type === 'token') {
        if (!tokenStarted) {
          tokenStarted = true
          progressMsg.completed = true
          // Auto-collapse thinking when answer starts
          if (thinkingStarted) thinkingMsg.visible = false
          assistantMsg.visible = true
        }
        tokenBuf += ev.content || ''
        assistantMsg.content = tokenBuf
        scrollToBottom()
      } else if (ev.type === 'error') {
        progressMsg.failed = true
        assistantMsg.visible = true
        assistantMsg.content = `<span class="text-red-500">错误: ${escapeHtml(ev.message)}</span>`
      }
    })

    // Cleanup
    if (!tokenStarted) {
      const idx = messages.value.indexOf(assistantMsg)
      if (idx > -1) messages.value.splice(idx, 1)
    }
    if (!thinkingStarted) {
      const idx = messages.value.indexOf(thinkingMsg)
      if (idx > -1) messages.value.splice(idx, 1)
    }
  } catch (e) {
    progressMsg.failed = true
    assistantMsg.visible = true
    assistantMsg.content = `<span class="text-red-500">网络错误: ${e.message}</span>`
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="max-w-3xl mx-auto">
    <div
      ref="msgContainer"
      class="space-y-4 mb-4 min-h-[400px] max-h-[500px] overflow-y-auto p-3 bg-slate-50 rounded-lg border"
    >
      <div v-if="messages.length === 0" class="text-center text-slate-400 italic text-sm">
        基于知识库回答你的运维问题
      </div>

      <template v-for="(m, i) in messages" :key="i">
        <ChatMessage
          v-if="m.type === 'msg' && m.visible !== false"
          :role="m.role"
          :content="m.content"
        />
        <ThinkingBubble
          v-else-if="m.type === 'thinking' && m.visible"
          :content="m.content"
        />
        <ProgressBubble
          v-else-if="m.type === 'progress'"
          :rows="m.rows"
          :completed="m.completed"
          :failed="m.failed"
        />
      </template>
    </div>

    <ChatInput
      :web-enabled="chatWebEnabled"
      :mcp-enabled="chatMcpEnabled"
      @send="send"
      @toggle-web="chatWebEnabled = !chatWebEnabled"
      @toggle-mcp="chatMcpEnabled = !chatMcpEnabled"
    />
  </div>
</template>
