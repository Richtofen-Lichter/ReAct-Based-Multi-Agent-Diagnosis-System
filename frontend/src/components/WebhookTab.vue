<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../composables/useApi.js'
import { renderMarkdown, escapeHtml } from '../composables/useMarkdown.js'

const { get, post, del } = useApi()

// ==================== 测试场景 ====================
const SCENARIOS = [
  { key: 'redis',   label: 'Redis 内存高',       alertname: 'RedisMemoryHigh',   severity: 'critical', service: 'redis',           instance: 'redis-master-01:6379',      summary: 'Redis 实例内存使用率 98%',            description: '实例内存接近上限，连接被断开，需立即排查内存使用情况' },
  { key: 'disk',    label: '磁盘空间不足',        alertname: 'DiskSpaceLow',      severity: 'critical', service: 'node',             instance: 'k8s-node-03:9100',           summary: '节点磁盘空间不足 5%',                  description: '磁盘使用率已达到 95%，预计 2 小时内写满' },
  { key: 'cpu',     label: 'CPU 使用率高',        alertname: 'CPUHighUsage',      severity: 'warning',  service: 'app-server',       instance: 'app-server-07:9100',          summary: '服务器 CPU 使用率持续 92%',            description: '过去 15 分钟 CPU 持续高于 90%，服务响应延迟上升' },
  { key: 'memory',  label: '进程内存泄漏',        alertname: 'ProcessMemoryLeak', severity: 'warning',  service: 'payment-service',  instance: 'payment-svc-pod-x9f3:8080',   summary: 'payment-service Pod 内存泄漏迹象',    description: 'Pod 内存使用持续增长，未见释放，疑似内存泄漏' },
  { key: 'kafka',   label: 'Kafka ISR 抖动',      alertname: 'KafkaISRShrinking', severity: 'warning',  service: 'kafka',           instance: 'kafka-broker-02:9092',        summary: 'Kafka ISR 列表频繁抖动',              description: 'ISR 列表在过去 10 分钟内缩扩容交替 5 次' },
]

const selectedScenario = ref('redis')
const sending = ref(false)
const sendResult = ref(null) // { ok, message, triggered, skipped }

// ==================== 历史记录 ====================
const history = ref([])
const loading = ref(false)
const error = ref('')
const expandedId = ref(null)
const clearing = ref(false)
const lastRefresh = ref('')

function formatTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDuration(started, finished) {
  if (!started || !finished) return '-'
  const s = new Date(started).getTime()
  const f = new Date(finished).getTime()
  const sec = Math.round((f - s) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  return `${min}m${sec % 60}s`
}

const severityClass = (s) => s === 'critical' ? 'bg-red-100 text-red-700 border-red-300' : 'bg-yellow-100 text-yellow-700 border-yellow-300'

// ==================== API 调用 ====================
async function sendAlert() {
  sending.value = true
  sendResult.value = null
  try {
    const sc = SCENARIOS.find(s => s.key === selectedScenario.value)
    const payload = {
      version: '4',
      status: 'firing',
      receiver: 'multi-agent-aiops',
      alerts: [{
        status: 'firing',
        labels: {
          alertname: sc.alertname,
          severity: sc.severity,
          service: sc.service,
          instance: sc.instance,
        },
        annotations: {
          summary: sc.summary,
          description: sc.description,
        },
        startsAt: new Date().toISOString(),
        fingerprint: crypto.randomUUID().replace(/-/g, '').slice(0, 16),
      }],
    }
    const data = await post('/webhook/alertmanager', payload)
    sendResult.value = {
      ok: true,
      message: `已入队 ${data.triggered?.length || 0} 条 Celery 任务，跳过 ${data.skipped?.length || 0} 条`,
      triggered: data.triggered || [],
      skipped: data.skipped || [],
    }
  } catch (e) {
    sendResult.value = { ok: false, message: `发送失败: ${e.message}`, triggered: [], skipped: [] }
  } finally {
    sending.value = false
  }
}

async function fetchHistory() {
  loading.value = true
  error.value = ''
  try {
    const data = await get('/webhook/history?limit=50')
    history.value = data?.items || []
    lastRefresh.value = formatTime(new Date().toISOString())
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function clearHistory() {
  if (!confirm('确定清空所有诊断历史记录吗？此操作不可撤销。')) return
  clearing.value = true
  try {
    await del('/webhook/history')
    history.value = []
    lastRefresh.value = formatTime(new Date().toISOString())
  } catch (e) {
    alert(`清空失败: ${e.message}`)
  } finally {
    clearing.value = false
  }
}

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

onMounted(() => {
  fetchHistory()
})
</script>

<template>
  <div class="space-y-6">
    <!-- ========== 测试触发器 ========== -->
    <div class="border rounded-xl p-5 bg-gradient-to-br from-slate-50 to-indigo-50/30">
      <h3 class="text-sm font-semibold text-slate-600 mb-4">🧪 一键测试告警</h3>
      <p class="text-xs text-slate-500 mb-4">
        模拟 Alertmanager 发送一条 Webhook 告警，后台自动走完整 AIOps 诊断链路（SkillRouter → Planner → Executor → Replanner → Report）。
        诊断完成后在下方历史列表中查看结果。
      </p>

      <!-- 场景选择 -->
      <div class="flex flex-wrap gap-2 mb-4">
        <button
          v-for="sc in SCENARIOS"
          :key="sc.key"
          :class="[
            'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
            selectedScenario === sc.key
              ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
              : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300 hover:text-indigo-600'
          ]"
          @click="selectedScenario = sc.key"
        >
          {{ sc.label }}
          <span
            :class="[
              'ml-1.5 inline-block w-1.5 h-1.5 rounded-full',
              sc.severity === 'critical' ? 'bg-red-400' : 'bg-yellow-400'
            ]"
          ></span>
        </button>
      </div>

      <!-- 选中场景详情 -->
      <div class="text-xs text-slate-500 mb-4 bg-white rounded-lg p-3 border">
        <template v-for="sc in SCENARIOS" :key="sc.key">
          <div v-if="sc.key === selectedScenario" class="space-y-1">
            <div><span class="text-slate-400">告警名:</span> <code class="text-slate-700">{{ sc.alertname }}</code></div>
            <div><span class="text-slate-400">严重级别:</span>
              <span :class="['inline-block px-1.5 py-0.5 rounded text-xs font-medium border', severityClass(sc.severity)]">{{ sc.severity }}</span>
            </div>
            <div><span class="text-slate-400">实例:</span> {{ sc.instance }}</div>
            <div><span class="text-slate-400">摘要:</span> {{ sc.summary }}</div>
          </div>
        </template>
      </div>

      <button
        class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
        :disabled="sending"
        @click="sendAlert"
      >
        <span v-if="sending" class="inline-flex items-center gap-2">
          <span class="animate-spin text-xs">⏳</span> 发送中...
        </span>
        <span v-else>🚀 发送测试告警</span>
      </button>

      <!-- 发送结果 -->
      <div
        v-if="sendResult"
        :class="[
          'mt-4 text-sm rounded-lg p-3 border',
          sendResult.ok ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'
        ]"
      >
        <p class="font-medium">{{ sendResult.ok ? '✓' : '✗' }} {{ sendResult.message }}</p>
        <ul v-if="sendResult.triggered.length" class="mt-1 text-xs space-y-0.5">
          <li v-for="t in sendResult.triggered" :key="t.task_id || t" class="font-mono">
            <span v-if="typeof t === 'object'">{{ t.session_id }} <span class="text-slate-400">(task: {{ t.task_id?.slice(0,8) }}...)</span></span>
            <span v-else>{{ t }}</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- ========== 诊断历史 ========== -->
    <div class="border rounded-xl p-5">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-sm font-semibold text-slate-600">📋 全自动诊断历史</h3>
        <div class="flex items-center gap-3">
          <span v-if="lastRefresh" class="text-xs text-slate-400">上次刷新: {{ lastRefresh }}</span>
          <button
            class="text-xs text-indigo-600 hover:underline"
            :disabled="loading"
            @click="fetchHistory"
          >🔄 刷新</button>
          <button
            v-if="history.length > 0"
            class="text-xs text-red-500 hover:underline"
            :disabled="clearing"
            @click="clearHistory"
          >{{ clearing ? '清空中...' : '🗑 清空历史' }}</button>
        </div>
      </div>

      <!-- loading / error / empty -->
      <div v-if="loading" class="text-center py-12 text-slate-400 text-sm italic">加载中...</div>
      <div v-else-if="error" class="text-center py-12 text-red-500 text-sm">{{ error }}</div>
      <div v-else-if="history.length === 0" class="text-center py-12 text-slate-400 text-sm">
        <p class="text-lg mb-1">📭</p>
        <p>暂无自动诊断记录</p>
        <p class="text-xs mt-1">通过上方「一键测试告警」发送一条，或等待 Alertmanager Webhook 自动触发</p>
      </div>

      <!-- 历史列表 -->
      <div v-else class="space-y-3 max-h-[640px] overflow-y-auto">
        <div
          v-for="item in history"
          :key="item.session_id"
          :class="[
            'border rounded-lg transition-colors',
            item.error ? 'border-red-300 bg-red-50/50' : 'border-slate-200 hover:border-indigo-200'
          ]"
        >
          <!-- 卡片头部 (可点击展开) -->
          <div
            class="flex items-center gap-3 px-4 py-3 cursor-pointer select-none"
            @click="toggleExpand(item.session_id)"
          >
            <!-- 展开图标 -->
            <span class="text-xs text-slate-400 transition-transform" :class="{ 'rotate-90': expandedId === item.session_id }">▶</span>

            <!-- alertname -->
            <span class="text-sm font-semibold text-slate-700 min-w-0 truncate">{{ escapeHtml(item.alert?.alertname || 'Unknown') }}</span>

            <!-- severity badge -->
            <span
              v-if="item.alert?.severity"
              :class="['text-xs px-1.5 py-0.5 rounded border font-medium shrink-0', severityClass(item.alert.severity)]"
            >{{ item.alert.severity }}</span>

            <!-- instance -->
            <span class="text-xs text-slate-500 truncate min-w-0 hidden sm:inline" :title="item.alert?.instance">{{ item.alert?.instance || '-' }}</span>

            <!-- skill -->
            <span class="text-xs text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded shrink-0 hidden md:inline">
              {{ item.selected_skill || '待选择' }}
            </span>

            <!-- 事件数 -->
            <span class="text-xs text-slate-400 shrink-0 hidden lg:inline">{{ item.event_count || 0 }} 事件</span>

            <!-- 耗时 -->
            <span class="text-xs text-slate-400 shrink-0 ml-auto">{{ formatDuration(item.started_at, item.finished_at) }}</span>

            <!-- 时间 -->
            <span class="text-xs text-slate-400 shrink-0 hidden sm:inline w-[140px] text-right">{{ formatTime(item.started_at) }}</span>

            <!-- 错误标记 -->
            <span v-if="item.error" class="text-xs text-red-500 shrink-0" :title="item.error">⚠️ 失败</span>
          </div>

          <!-- 展开内容 -->
          <div v-if="expandedId === item.session_id" class="px-4 pb-4 border-t border-slate-100">
            <!-- 错误信息 -->
            <div v-if="item.error" class="mt-3 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
              <span class="font-medium">诊断失败:</span> {{ item.error }}
            </div>

            <!-- 元信息 -->
            <div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs text-slate-500">
              <div><span class="text-slate-400">Session</span><br><code class="text-slate-600 text-[11px]">{{ item.session_id }}</code></div>
              <div><span class="text-slate-400">开始时间</span><br>{{ formatTime(item.started_at) }}</div>
              <div><span class="text-slate-400">完成时间</span><br>{{ formatTime(item.finished_at) }}</div>
              <div><span class="text-slate-400">已选 Skill</span><br>{{ item.selected_skill || '(未选中)' }}</div>
            </div>

            <!-- 送入诊断的 query -->
            <details class="mt-3 text-xs text-slate-500">
              <summary class="cursor-pointer text-slate-400">查看送入诊断的 Query</summary>
              <pre class="mt-1 bg-slate-50 p-2 rounded text-xs whitespace-pre-wrap">{{ item.query }}</pre>
            </details>

            <!-- 诊断报告 -->
            <div v-if="item.report" class="mt-3">
              <div class="text-xs text-slate-400 mb-1 font-medium">诊断报告</div>
              <div
                class="prose prose-sm max-w-none border rounded-lg p-4 bg-white max-h-[500px] overflow-y-auto"
                v-html="renderMarkdown(item.report)"
              ></div>
            </div>
            <div v-else-if="!item.error" class="mt-3 text-xs text-slate-400 italic">(诊断进行中或未生成报告)</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
