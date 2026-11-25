<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { toast } from '../store'
import Icon from './Icon.vue'
import Modal from './Modal.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  room: { type: Object, default: null },
  draft: { type: Boolean, default: false },
  initialWindows: { type: Array, default: () => [] }
})
const emit = defineEmits(['close', 'saved'])

const WEEKDAYS = [
  { value: 0, label: '周一', short: '一' },
  { value: 1, label: '周二', short: '二' },
  { value: 2, label: '周三', short: '三' },
  { value: 3, label: '周四', short: '四' },
  { value: 4, label: '周五', short: '五' },
  { value: 5, label: '周六', short: '六' },
  { value: 6, label: '周日', short: '日' }
]

const windows = ref([])
const selectedDays = ref([0, 1, 2, 3, 4])
const start = ref('19:30')
const end = ref('23:30')
const loading = ref(false)
const saving = ref(false)
const error = ref('')

const roomLabel = computed(() => props.draft
  ? '新直播间'
  : (props.room?.custom_name || props.room?.last_anchor_name || props.room?.url || ''))

watch(() => props.open, async (open) => {
  if (!open) return
  error.value = ''
  if (props.draft) {
    windows.value = (props.initialWindows || []).map((item) => ({
      weekdays: [...item.weekdays],
      start: item.start,
      end: item.end
    }))
    loading.value = false
    return
  }
  loading.value = true
  try {
    const data = await api(`/rooms/${props.room.id}/schedule`)
    windows.value = data.windows || []
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
})

function toggleDay(day) {
  const set = new Set(selectedDays.value)
  if (set.has(day)) set.delete(day)
  else set.add(day)
  selectedDays.value = [...set].sort((a, b) => a - b)
}

function weekdayText(days) {
  const sorted = [...days].sort((a, b) => a - b)
  if (sorted.length === 7) return '每天'
  const groups = []
  let begin = sorted[0]
  let previous = sorted[0]
  for (const day of sorted.slice(1)) {
    if (day === previous + 1) { previous = day; continue }
    groups.push([begin, previous])
    begin = previous = day
  }
  groups.push([begin, previous])
  return groups.map(([a, b]) => {
    if (a === b) return WEEKDAYS[a].label
    if (b === a + 1) return `${WEEKDAYS[a].label}、${WEEKDAYS[b].label}`
    return `${WEEKDAYS[a].label}至${WEEKDAYS[b].label}`
  }).join('、')
}

function crossesMidnight(item) {
  return item.end <= item.start
}

function addWindow() {
  error.value = ''
  if (!selectedDays.value.length) { error.value = '请至少选择一个星期'; return }
  if (!start.value || !end.value) { error.value = '请选择开始与结束时间'; return }
  if (start.value === end.value) { error.value = '开始时间与结束时间不能相同'; return }
  if (windows.value.some((item) => item.start === start.value && item.end === end.value
      && item.weekdays.join(',') === selectedDays.value.join(','))) {
    error.value = '该时间段已存在'; return
  }
  if (windows.value.length >= 20) { error.value = '单个直播间最多 20 个时间段'; return }
  windows.value.push({ weekdays: [...selectedDays.value], start: start.value, end: end.value })
}

function removeWindow(index) {
  windows.value.splice(index, 1)
}

async function save() {
  saving.value = true
  error.value = ''
  const payload = windows.value.map(({ weekdays, start: begin, end: finish }) => ({
    weekdays, start: begin, end: finish
  }))
  if (props.draft) {
    emit('saved', payload)
    emit('close')
    saving.value = false
    return
  }
  try {
    await api(`/rooms/${props.room.id}/schedule`, { method: 'PUT', body: { windows: payload } })
    toast('录制计划已保存', 'success')
    emit('saved')
    emit('close')
  } catch (err) {
    error.value = err.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal :open="open" title="录制计划" wide @close="emit('close')">
    <div class="schedule-editor">
      <div class="schedule-intro">
        <div>
          <div class="schedule-intro-title">{{ roomLabel }}</div>
          <p class="field-hint">
            {{ draft ? '时间段会随直播间一起保存，留空表示全天录制。' : '未添加时间段时全天检测与录制；时段外不请求平台接口。' }}
          </p>
        </div>
        <span class="schedule-tz"><Icon name="clock" :size="14" /> 服务器时区</span>
      </div>

      <div v-if="loading" class="schedule-loading">
        <div class="skeleton" style="height:38px" />
        <div class="skeleton" style="height:64px" />
      </div>

      <template v-else>
        <div class="schedule-compose">
          <div class="schedule-field">
            <span class="schedule-label">星期</span>
            <div class="day-pills" role="group" aria-label="选择星期">
              <button v-for="day in WEEKDAYS" :key="day.value" type="button" class="day-pill"
                      :class="{ active: selectedDays.includes(day.value) }"
                      :aria-pressed="selectedDays.includes(day.value)"
                      @click="toggleDay(day.value)">
                {{ day.short }}
              </button>
            </div>
          </div>
          <div class="schedule-time-row">
            <label class="schedule-field">
              <span class="schedule-label">开始</span>
              <input v-model="start" type="time" class="input" step="60" />
            </label>
            <span class="schedule-time-sep">至</span>
            <label class="schedule-field">
              <span class="schedule-label">结束</span>
              <input v-model="end" type="time" class="input" step="60" />
            </label>
            <button type="button" class="btn btn-primary schedule-add" @click="addWindow">
              <Icon name="plus" :size="15" /> 添加时间段
            </button>
          </div>
          <p v-if="start && end && end <= start" class="schedule-cross-hint">
            结束时间早于开始时间，将按跨天时段处理（次日 {{ end }} 结束）。
          </p>
        </div>

        <div class="schedule-list-head">
          <span>已添加的时间段</span>
          <span class="cell-muted">{{ windows.length }} / 20</span>
        </div>
        <TransitionGroup v-if="windows.length" name="schedule-row" tag="ul" class="schedule-list">
          <li v-for="(item, index) in windows" :key="`${item.weekdays.join('-')}-${item.start}-${item.end}-${index}`"
              class="schedule-window">
            <span class="schedule-window-days">{{ weekdayText(item.weekdays) }}</span>
            <span class="schedule-window-time">{{ item.start }} - {{ item.end }}</span>
            <span v-if="crossesMidnight(item)" class="badge warning">次日</span>
            <span class="schedule-window-spacer" />
            <button type="button" class="btn btn-icon btn-ghost" title="删除时间段" aria-label="删除时间段"
                    @click="removeWindow(index)">
              <Icon name="trash" :size="15" />
            </button>
          </li>
        </TransitionGroup>
        <div v-else class="schedule-empty">
          <Icon name="clock" :size="20" />
          <span>未设置时间窗，当前全天允许录制</span>
        </div>

        <div v-if="error" class="form-error" role="alert">{{ error }}</div>
      </template>
    </div>

    <template #footer>
      <button class="btn" :disabled="saving" @click="emit('close')">取消</button>
      <button class="btn btn-primary" :disabled="loading || saving" @click="save">
        {{ saving ? '保存中…' : '保存计划' }}
      </button>
    </template>
  </Modal>
</template>
