<script setup>
import { ref } from 'vue'
import HealthIndicator from './components/HealthIndicator.vue'
import AiopsTab from './components/AiopsTab.vue'
import ChatTab from './components/ChatTab.vue'
import DocumentsTab from './components/DocumentsTab.vue'
import WebhookTab from './components/WebhookTab.vue'

const activeTab = ref('aiops')
</script>

<template>
  <!-- Header -->
  <header class="bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg">
    <div class="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Multi-Agent AIOps Platform</h1>
        <p class="text-indigo-100 text-sm">企业级智能运维诊断 · LangGraph + RAG + MCP</p>
      </div>
      <HealthIndicator />
    </div>
  </header>

  <!-- Tabs -->
  <div class="max-w-7xl mx-auto px-6 mt-6">
    <div class="bg-white rounded-t-xl shadow-sm border-b">
      <nav class="flex space-x-1 px-2 pt-2">
        <button
          :class="['tab-btn', { 'tab-active': activeTab === 'aiops' }]"
          @click="activeTab = 'aiops'"
        >🔍 AIOps 诊断</button>
        <button
          :class="['tab-btn', { 'tab-active': activeTab === 'chat' }]"
          @click="activeTab = 'chat'"
        >💬 RAG 聊天</button>
        <button
          :class="['tab-btn', { 'tab-active': activeTab === 'documents' }]"
          @click="activeTab = 'documents'"
        >📚 知识库</button>
        <button
          :class="['tab-btn', { 'tab-active': activeTab === 'webhook' }]"
          @click="activeTab = 'webhook'"
        >📡 Webhook 诊断</button>
      </nav>
    </div>
    <div class="bg-white rounded-b-xl shadow-md p-6 min-h-[600px]">
      <AiopsTab v-show="activeTab === 'aiops'" />
      <ChatTab v-show="activeTab === 'chat'" />
      <DocumentsTab v-show="activeTab === 'documents'" />
      <WebhookTab v-show="activeTab === 'webhook'" />
    </div>
  </div>

  <footer class="text-center text-xs text-slate-400 py-6">
    Multi-Agent AIOps · LangChain v1.x · 2026
  </footer>
</template>
