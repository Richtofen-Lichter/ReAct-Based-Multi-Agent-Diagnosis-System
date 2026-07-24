<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { consumeSSE } from '../composables/useSSE.js'
import { renderMarkdown, escapeHtml } from '../composables/useMarkdown.js'
import { useSkills } from '../composables/useSkills.js'
import SkillPanel from './SkillPanel.vue'
import QueryInput from './QueryInput.vue'
import PlanPanel from './PlanPanel.vue'
import StepList from './StepList.vue'
import MonitorPanel from './MonitorPanel.vue'
import ReportPanel from './ReportPanel.vue'

const API = '/api/v1'

const {
  skills, loading: skillsLoading, error: skillsError,
  selectedSkill, selectedSkillDisplay, selectedReason,
  loadSkills, highlightSkill, clearHighlight,
} = useSkills()

// Query
const query = ref('我的电脑内存占用居高不下, 系统明显卡顿, 浏览器和开发工具响应变慢, 已持续 12 分钟')
const running = ref(false)

// fast/deep 诊断模式 (与后端 DiagnosisMode 对齐)
const diagnosisMode = ref('fast')  // 'fast' | 'deep'
const modeBadge = ref('')          // mode_selected 事件回填: deep 回落 fast 时显示降级提示

// Plan
const plan = ref([])

// Steps
const steps = ref([])

// Monitor
const monitor = reactive({
  step: '—',
  stepLabel: '等待启动',
  elapsed: '0.0',
  toolCount: 0,
  toolFail: 0,
  tokens: 0,
  tokensDetail: '输入 0 · 输出 0',
  tokensTooltip: '',
  hasRealUsage: false,
  streamHint: '等待中',
  streamContent: '',
  toolFeed: [],
})

// Deep 取证时间线 (evidence / candidates / rca / remediation / evidence_plan)
const deepFeed = ref([])

// Report
const reportHtml = ref('')
const showReport = ref(false)

// Status
const status = ref('未开始')

// Timer & Abort
let monTimer = null
let monStartTs = 0
let monTokenCount = 0
let monRealInput = 0
let monRealOutput = 0
let monRealTotal = 0
let monCacheHit = 0
let monCacheMiss = 0
let monHasReal = false
let abortController = null

function resetMonitor() {
  monStartTs = Date.now()
  monTokenCount = 0
  monRealInput = 0
  monRealOutput = 0
  monRealTotal = 0
  monCacheHit = 0
  monCacheMiss = 0
  monHasReal = false
  Object.assign(monitor, {
    step: '—',
    stepLabel: 'Skill Router 工作中...',
    elapsed: '0.0',
    toolCount: 0,
    toolFail: 0,
    tokens: 0,
    tokensDetail: '输入 0 · 输出 0',
    tokensTooltip: '',
    hasRealUsage: false,
    streamHint: '等待中',
    streamContent: '',
    toolFeed: [],
  })
  if (monTimer) clearInterval(monTimer)
  monTimer = setInterval(() => {
    monitor.elapsed = ((Date.now() - monStartTs) / 1000).toFixed(1)
  }, 100)
}

function stopMonitor() {
  if (monTimer) {
    clearInterval(monTimer)
    monTimer = null
  }
}

function showMonitorPanel() {
  showReport.value = false
}

function showReportPanel() {
  showReport.value = true
}

// SSE event handler
function handleAIOpsEvent(ev) {
  const t = ev.type
  const d = ev.data || {}

  if (t !== 'transition') {
    console.log('[AIOps SSE]', t, d)
  }

  switch (t) {
    case 'start':
      status.value = 'Skill Router 工作中...'
      break

    case 'transition': {
      // 节点出口 transition (含 deep 图 DEEP_* 各节点进度). deep 模式下推到时间线.
      const reason = d.reason || ''
      if (reason.startsWith('deep_')) {
        deepFeed.value.push({
          kind: 'transition', label: d.node || '',
          detail: reason + (d.message ? ` · ${d.message}` : ''),
        })
      }
      break
    }

    case 'mode_selected':
      // 后端告知最终跑哪个图 + deep 是否被降级 (group_agent_reserved)
      modeBadge.value = d.group_agent_reserved
        ? '⚠️ deep 未启用, 已降级 fast'
        : (d.effective_mode === 'deep' ? '深度诊断图' : 'fast 模式')
      status.value = d.message || status.value
      break

    case 'skill_selected':
      highlightSkill(d.skill, d.reason)
      status.value = `已选 Skill: ${d.skill || '(无)'}, Planner 工作中...`
      break

    case 'plan': {
      plan.value = d.plan || []
      status.value = `已生成 ${plan.value.length} 步计划`
      break
    }

    case 'step_start': {
      let existing = steps.value.find(s => s.iteration === d.iteration)
      if (!existing) {
        steps.value.push({
          iteration: d.iteration,
          title: d.step || '',
          streamContent: '',
          status: 'executing',
          resultPreview: '',
        })
      }
      status.value = `正在执行第 ${d.iteration} 步...`
      monitor.step = String(d.iteration)
      monitor.stepLabel = (d.step || '').slice(0, 40)
      monitor.streamHint = '生成中...'
      monitor.streamContent = ''
      break
    }

    case 'step_token': {
      const iter = d.iteration || 0
      const content = d.content || ''
      let s = steps.value.find(s => s.iteration === iter)
      if (!s) {
        s = { iteration: iter, title: '', streamContent: '', status: 'executing', resultPreview: '' }
        steps.value.push(s)
      }
      s.streamContent += content
      if (s.streamContent.length > 2000) {
        s.streamContent = '...' + s.streamContent.slice(-1800)
      }

      // Monitor stream
      monitor.streamContent += content
      if (monitor.streamContent.length > 4000) {
        monitor.streamContent = '...' + monitor.streamContent.slice(-3600)
      }

      monTokenCount += content.length
      if (!monHasReal) {
        monitor.tokens = monTokenCount
        monitor.tokensDetail = `~流字符 ${monTokenCount}`
      }
      break
    }

    case 'usage':
      monHasReal = true
      monitor.hasRealUsage = true
      monRealInput += d.input_tokens || 0
      monRealOutput += d.output_tokens || 0
      monRealTotal += d.total_tokens || 0
      if (d.cache_hit_tokens != null) monCacheHit += d.cache_hit_tokens
      if (d.cache_miss_tokens != null) monCacheMiss += d.cache_miss_tokens

      monitor.tokens = monRealOutput
      const parts = [`输入 ${monRealInput}`, `输出 ${monRealOutput}`]
      if (monCacheHit > 0 || monCacheMiss > 0) {
        parts.push(`缓存命中 ${monCacheHit}`)
      }
      monitor.tokensDetail = parts.join(' · ')
      monitor.tokensTooltip = `合计 ${monRealTotal} tokens` + (d.model ? ` · ${d.model}` : '')
      break

    case 'tool_call': {
      const ok = d.success !== false
      monitor.toolCount++
      if (!ok) monitor.toolFail++
      monitor.toolFeed.push({
        ok,
        name: d.name || '?',
        elapsed: d.elapsed_ms != null ? `${d.elapsed_ms}ms` : '',
      })
      break
    }

    // ===== Deep 图结构化事件: 累加进 deepFeed 时间线 (fast 模式不发这些) =====
    case 'evidence_plan':
      deepFeed.value.push({
        kind: 'plan', label: '取证计划',
        detail: `派出 ${(d.agents || []).join(' / ') || '(无)'} · ${d.strategy || ''}`,
      })
      break
    case 'evidence':
      deepFeed.value.push({
        kind: 'evidence', label: `证据 · ${d.agent || ''}`,
        detail: d.message || '',
      })
      break
    case 'candidates':
      deepFeed.value.push({
        kind: 'candidates', label: '候选根因',
        detail: `归并 ${(d.candidates || []).length} 个候选`,
      })
      break
    case 'rca':
      deepFeed.value.push({
        kind: 'rca', label: 'RCA 判定',
        detail: d.message || (d.rca && d.rca.root_cause) || '',
      })
      break
    case 'remediation':
      deepFeed.value.push({
        kind: 'remediation', label: '处置建议',
        detail: d.message || '',
      })
      break

    case 'step_complete': {
      const iter = d.iteration || 0
      let s = steps.value.find(s => s.iteration === iter)
      if (s) {
        s.status = 'done'
        s.resultPreview = (d.result_preview || '').slice(0, 200)
      }
      status.value = `已完成 ${d.iteration} 步`
      break
    }

    case 'replan':
      steps.value.push({
        iteration: Date.now(),
        title: '',
        streamContent: '',
        status: 'replan',
        remainingSteps: (d.plan || []).length,
        resultPreview: '',
      })
      break

    case 'report':
      showReportPanel()
      reportHtml.value = renderMarkdown(d.report || '')
      status.value = '报告已生成'
      monitor.streamHint = '已完成'
      break

    case 'complete':
      status.value = '完成 ✓'
      break

    case 'error':
      showReportPanel()
      reportHtml.value = `<p class="text-red-500">错误: ${escapeHtml(ev.message)}</p>`
      status.value = '失败 ✗'
      break
  }
}

async function start() {
  const q = query.value.trim()
  if (!q) return alert('请输入告警内容')

  plan.value = []
  steps.value = []
  reportHtml.value = ''
  modeBadge.value = ''
  deepFeed.value = []
  showMonitorPanel()
  resetMonitor()
  status.value = 'Skill Router 工作中...'
  clearHighlight()

  running.value = true
  abortController = new AbortController()

  try {
    const resp = await fetch(`${API}/aiops/diagnose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: `web-${Date.now()}`,
        query: q,
        diagnosis_mode: diagnosisMode.value,
      }),
      signal: abortController.signal,
    })
    await consumeSSE(resp, handleAIOpsEvent)
    status.value = '完成 ✓'
  } catch (e) {
    if (e.name === 'AbortError') {
      status.value = '已停止'
    } else {
      status.value = '失败 ✗'
      showReportPanel()
      reportHtml.value = `<p class="text-red-500">错误: ${e.message}</p>`
    }
  } finally {
    running.value = false
    abortController = null
    stopMonitor()
  }
}

function stop() {
  if (abortController) abortController.abort()
}

onMounted(() => {
  loadSkills()
})

onUnmounted(() => {
  stopMonitor()
  if (abortController) abortController.abort()
})
</script>

<template>
  <div>
    <!-- Skill Panel -->
    <SkillPanel
      :skills="skills"
      :loading="skillsLoading"
      :error="skillsError"
      :selected-skill="selectedSkill"
      :selected-skill-display="selectedSkillDisplay"
      :selected-reason="selectedReason"
    />

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-6 aiops-grid">
      <!-- 左侧: 输入 + 计划 + 步骤 -->
      <div class="xl:col-span-1 flex flex-col min-h-0 space-y-3">
        <!-- fast/deep 诊断模式切换 -->
        <div class="flex items-center gap-2 text-xs">
          <span class="font-semibold text-slate-600">诊断模式</span>
          <div class="inline-flex rounded-lg overflow-hidden border border-slate-300">
            <button
              type="button"
              :disabled="running"
              @click="diagnosisMode = 'fast'"
              :class="diagnosisMode === 'fast' ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'"
              class="px-3 py-1 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >日常 (fast)</button>
            <button
              type="button"
              :disabled="running"
              @click="diagnosisMode = 'deep'"
              :class="diagnosisMode === 'deep' ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'"
              class="px-3 py-1 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >深度 (deep)</button>
          </div>
          <span v-if="modeBadge" class="text-slate-400">{{ modeBadge }}</span>
        </div>

        <QueryInput v-model="query" :running="running" @start="start" @stop="stop" />

        <PlanPanel :plan="plan" />

        <StepList :steps="steps" />

        <!-- Deep 取证时间线 (仅 deep 模式有内容时显示) -->
        <div
          v-if="deepFeed.length"
          class="border rounded-lg bg-white p-3 space-y-1 max-h-64 overflow-y-auto"
        >
          <div class="text-xs font-semibold text-slate-600 mb-1">🔍 Deep 取证时间线</div>
          <div
            v-for="(item, i) in deepFeed"
            :key="i"
            class="text-xs flex items-start gap-2 border-b border-slate-100 last:border-0 py-1"
          >
            <span
              :class="{
                'text-indigo-600': item.kind === 'plan' || item.kind === 'transition',
                'text-emerald-600': item.kind === 'evidence',
                'text-amber-600': item.kind === 'candidates',
                'text-rose-600': item.kind === 'rca',
                'text-sky-600': item.kind === 'remediation',
              }"
              class="font-semibold shrink-0"
            >{{ item.label }}</span>
            <span class="text-slate-500 truncate">{{ item.detail }}</span>
          </div>
        </div>
      </div>

      <!-- 右侧: 监控 / 报告 -->
      <div class="col-span-2 flex flex-col min-h-0">
        <h3 class="text-sm font-semibold mb-2 text-slate-600 flex items-center justify-between shrink-0">
          <span>{{ showReport ? '📄 诊断报告' : '📊 诊断监控' }}</span>
          <span class="text-xs font-normal text-slate-400">{{ status }}</span>
        </h3>

        <MonitorPanel v-if="!showReport" :monitor="monitor" />
        <ReportPanel v-else :report-html="reportHtml" />
      </div>
    </div>
  </div>
</template>
