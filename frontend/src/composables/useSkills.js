/**
 * Skill 库 / Playbook 管理与高亮选中。
 */
import { ref } from 'vue'

const API = '/api/v1'

export const RISK_BADGE = {
  low:    { color: 'bg-emerald-100 text-emerald-700 border-emerald-200', label: '低风险' },
  medium: { color: 'bg-amber-100 text-amber-700 border-amber-200',       label: '中风险' },
  high:   { color: 'bg-red-100 text-red-700 border-red-200',             label: '高风险' },
}

export function useSkills() {
  const skills = ref([])
  const loading = ref(false)
  const error = ref('')
  const selectedSkill = ref('')
  const selectedSkillDisplay = ref('')
  const selectedReason = ref('')

  async function loadSkills() {
    loading.value = true
    error.value = ''
    try {
      const r = await fetch(`${API}/skills`)
      const data = await r.json()
      if (data?.code !== 'SUCCESS') throw new Error(data?.message || '加载 Skill 失败')
      skills.value = data?.data?.skills || []
    } catch (e) {
      error.value = e.message
      skills.value = []
    } finally {
      loading.value = false
    }
  }

  function highlightSkill(skillName, reason) {
    selectedSkill.value = skillName || ''
    selectedReason.value = reason || ''
    const skill = skills.value.find(s => s.name === skillName)
    selectedSkillDisplay.value = skill?.display_name || skillName || '(未知)'
  }

  function clearHighlight() {
    selectedSkill.value = ''
    selectedSkillDisplay.value = ''
    selectedReason.value = ''
  }

  return {
    skills, loading, error,
    selectedSkill, selectedSkillDisplay, selectedReason,
    loadSkills, highlightSkill, clearHighlight,
  }
}
