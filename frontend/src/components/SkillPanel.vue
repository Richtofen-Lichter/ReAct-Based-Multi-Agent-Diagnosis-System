<script setup>
import { computed } from 'vue'
import { RISK_BADGE } from '../composables/useSkills.js'
import { escapeHtml } from '../composables/useMarkdown.js'

const props = defineProps({
  skills: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  selectedSkill: { type: String, default: '' },
  selectedSkillDisplay: { type: String, default: '' },
  selectedReason: { type: String, default: '' },
})

const hasSelection = computed(() => !!props.selectedSkill)
const skillCount = computed(() => props.skills.length)
</script>

<template>
  <div class="mb-5 bg-gradient-to-br from-slate-50 to-indigo-50 border rounded-lg p-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-slate-700 flex items-center">
        <span class="mr-1">🎯</span> Skill 库 (Playbook)
        <span class="ml-2 text-xs font-normal text-slate-500">· {{ skillCount }} 个</span>
      </h3>
      <div
        :class="['text-xs bg-indigo-600 text-white px-3 py-1 rounded-full', { hidden: !hasSelection }]"
      >
        <span class="opacity-80">本次诊断:</span>
        <span class="font-semibold">{{ selectedSkillDisplay }}</span>
      </div>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2 text-xs">
      <span class="text-slate-400 italic col-span-full">加载中...</span>
    </div>
    <div v-else-if="error" class="text-xs text-red-500">{{ error }}</div>
    <div v-else-if="skills.length === 0" class="text-xs text-slate-400 italic">暂无 Skill 注册</div>

    <!-- Skill Grid -->
    <div v-else class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2 text-xs">
      <div
        v-for="s in skills"
        :key="s.name"
        :class="[
          'skill-card border rounded-lg p-2 bg-white',
          RISK_BADGE[s.risk_level]?.color || RISK_BADGE.low.color,
          { 'skill-active': selectedSkill === s.name },
        ]"
        :title="s.display_name || s.name"
      >
        <div class="font-semibold truncate">{{ escapeHtml(s.display_name) }}</div>
        <div class="text-[10px] opacity-70 font-mono truncate">{{ escapeHtml(s.name) }}</div>
      </div>
    </div>

    <div
      :class="['mt-2 text-xs text-slate-600 italic', { hidden: !hasSelection || !selectedReason }]"
    >{{ selectedReason }}</div>
  </div>
</template>
