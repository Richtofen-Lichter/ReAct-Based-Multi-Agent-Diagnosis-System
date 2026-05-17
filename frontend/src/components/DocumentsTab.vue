<script setup>
import { ref, onMounted } from 'vue'
import UploadZone from './UploadZone.vue'
import DocumentList from './DocumentList.vue'

const API = '/api/v1'
const KB_ADMIN_TOKEN_KEY = 'multi_agent_kb_admin_token'

const documents = ref([])
const docsLoading = ref(false)
const docsError = ref('')

const uploadRef = ref(null)

function getKbAdminToken() {
  let token = sessionStorage.getItem(KB_ADMIN_TOKEN_KEY) || ''
  if (!token) {
    token = prompt('请输入知识库管理员 Token') || ''
    token = token.trim()
    if (!token) throw new Error('未输入管理员 Token')
    sessionStorage.setItem(KB_ADMIN_TOKEN_KEY, token)
  }
  return token
}

async function loadDocs() {
  docsLoading.value = true
  docsError.value = ''
  try {
    const r = await fetch(`${API}/documents`)
    const data = await r.json()
    documents.value = data?.data?.documents || []
  } catch (e) {
    docsError.value = e.message
    documents.value = []
  } finally {
    docsLoading.value = false
  }
}

async function handleUpload(file) {
  if (!uploadRef.value) return
  uploadRef.value.resultMsg = `⏳ 上传 ${file.name} ...`
  uploadRef.value.resultOk = true
  uploadRef.value.uploading = true

  const formData = new FormData()
  formData.append('file', file)
  try {
    const r = await fetch(`${API}/documents/upload`, {
      method: 'POST',
      headers: { 'X-KB-Admin-Token': getKbAdminToken() },
      body: formData,
    })
    const data = await r.json().catch(() => null)
    if (!r.ok) {
      if (r.status === 401 || r.status === 403) sessionStorage.removeItem(KB_ADMIN_TOKEN_KEY)
      throw new Error(data?.detail || data?.message || `HTTP ${r.status}`)
    }
    if (data.code === 'SUCCESS') {
      uploadRef.value.resultMsg = `✓ 已索引 ${data.data.chunks_indexed} 个 chunk (${data.data.bytes} bytes)`
      uploadRef.value.resultOk = true
      loadDocs()
    } else {
      uploadRef.value.resultMsg = `✗ ${data?.message || '上传失败'}`
      uploadRef.value.resultOk = false
    }
  } catch (e) {
    uploadRef.value.resultMsg = `✗ ${e.message}`
    uploadRef.value.resultOk = false
  } finally {
    uploadRef.value.uploading = false
  }
}

async function handleDelete(source) {
  if (!confirm(`确认删除 ${source}?`)) return
  try {
    const r = await fetch(`${API}/documents/${encodeURIComponent(source)}`, {
      method: 'DELETE',
      headers: { 'X-KB-Admin-Token': getKbAdminToken() },
    })
    const data = await r.json().catch(() => null)
    if (!r.ok || data?.code !== 'SUCCESS') {
      if (r.status === 401 || r.status === 403) sessionStorage.removeItem(KB_ADMIN_TOKEN_KEY)
      throw new Error(data?.detail || data?.message || `HTTP ${r.status}`)
    }
    loadDocs()
  } catch (e) {
    alert(`删除失败: ${e.message}`)
  }
}

onMounted(() => {
  loadDocs()
})
</script>

<template>
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <UploadZone ref="uploadRef" @upload="handleUpload" />
    <DocumentList
      :documents="documents"
      :loading="docsLoading"
      :error="docsError"
      @refresh="loadDocs"
      @delete="handleDelete"
    />
  </div>
</template>
