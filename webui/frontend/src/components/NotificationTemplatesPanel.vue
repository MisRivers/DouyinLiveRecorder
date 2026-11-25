<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import Icon from './Icon.vue'
import InfoTip from './InfoTip.vue'

const props = defineProps({
  query: { type: String, default: '' }
})

const emit = defineEmits(['dirty-change'])

const data = ref({ channels: [], events: [] })
const form = reactive({})
const dirty = reactive(new Set())
const openEvents = ref(new Set())
const previews = reactive({})
const loading = ref(true)
const error = ref('')

const dirtyCount = computed(() => dirty.size)
const visibleEvents = computed(() => {
  const needle = props.query.trim().toLowerCase()
  if (!needle) return data.value.events
  return data.value.events.filter((event) =>
    `${event.name} ${event.event_code} ${event.title_template} ${event.content_template}`
      .toLowerCase().includes(needle))
})

function apply(dataValue) {
  data.value = { channels: dataValue.channels || [], events: dataValue.events || [] }
  for (const event of data.value.events) {
    form[event.event_code] = {
      enabled: !!event.enabled,
      title_template: event.title_template || '',
      content_template: event.content_template || ''
    }
  }
  dirty.clear()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    apply(await api('/notifications/templates'))
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function mark(code) {
  dirty.add(code)
}

function toggleOpen(code) {
  const set = new Set(openEvents.value)
  if (set.has(code)) set.delete(code)
  else set.add(code)
  openEvents.value = set
}

function setEnabled(event, value) {
  form[event.event_code].enabled = value
  if (value) openEvents.value = new Set([...openEvents.value, event.event_code])
  mark(event.event_code)
}

function resetEvent(event) {
  form[event.event_code].title_template = event.default_title || ''
  form[event.event_code].content_template = event.default_content || ''
  previews[event.event_code] = null
  mark(event.event_code)
}

function insertVariable(event, variable) {
  const value = form[event.event_code]
  const spacer = value.content_template && !value.content_template.endsWith('\n') ? ' ' : ''
  value.content_template = `${value.content_template}${spacer}{${variable}}`
  mark(event.event_code)
}

async function preview(event) {
  const value = form[event.event_code]
  try {
    previews[event.event_code] = await api('/notifications/preview', {
      method: 'POST',
      body: {
        event_code: event.event_code,
        title_template: value.title_template,
        content_template: value.content_template
      }
    })
  } catch (err) {
    toast(err.message, 'error')
  }
}

async function save() {
  if (!dirtyCount.value) return 0
  const changed = dirtyCount.value
  const events = data.value.events.map((event) => ({
    event_code: event.event_code,
    enabled: form[event.event_code].enabled,
    title_template: form[event.event_code].title_template.trim(),
    content_template: form[event.event_code].content_template.trim()
  }))
  try {
    apply(await api('/notifications/templates', { method: 'PUT', body: { events } }))
    return changed
  } catch (err) {
    error.value = err.message
    throw err
  }
}

function reset() {
  for (const event of data.value.events) {
    const saved = form[event.event_code]
    saved.enabled = !!event.enabled
    saved.title_template = event.title_template || ''
    saved.content_template = event.content_template || ''
    previews[event.event_code] = null
  }
  dirty.clear()
  error.value = ''
}

watch(dirtyCount, (value) => emit('dirty-change', value), { immediate: true })

async function refreshChannels() {
  try {
    const result = await api('/notifications/templates')
    data.value.channels = result.channels || []
  } catch { /* 渠道刷新失败不影响模板编辑 */ }
}

defineExpose({ save, reset, refreshChannels })

onMounted(load)
</script>

<template>
  <div class="auto-panel">
    <div class="auto-head">
      <div class="auto-head-title">
        <div class="card-title">
          通知模板
          <InfoTip text="六类录制事件独立开关，发送到“推送配置”中选择的渠道。同一事件 60 秒内只发送一次；录制异常 10 分钟内最多一次。" />
        </div>
      </div>
      <div class="auto-channels">
        <span class="auto-label">当前渠道</span>
        <template v-if="data.channels.length">
          <span v-for="channel in data.channels" :key="channel" class="channel-chip">{{ channel }}</span>
        </template>
        <span v-else class="cell-muted">未选择</span>
      </div>
    </div>

    <div v-if="!loading && !data.channels.length" class="notice-banner warning" role="status">
      <Icon name="alert" :size="16" />
      <div>
        <strong>尚未选择推送渠道</strong>
        <span>请先在“推送配置”选择渠道并完成参数，模板开启后才会实际发送。</span>
      </div>
    </div>

    <div v-if="loading" class="notice-list">
      <div v-for="n in 3" :key="n" class="notice-event">
        <div class="skeleton" style="height:20px;width:180px" />
      </div>
    </div>

    <div v-else class="notice-list">
      <section v-for="event in visibleEvents" :key="event.event_code" class="notice-event"
               :class="{ enabled: form[event.event_code]?.enabled, open: openEvents.has(event.event_code) }">
        <header class="notice-event-head" @click="toggleOpen(event.event_code)">
          <span class="notice-caret" :class="{ open: openEvents.has(event.event_code) }">
            <Icon name="down" :size="14" />
          </span>
          <span class="notice-event-name">{{ event.name }}</span>
          <span class="notice-event-code mono">{{ event.event_code }}</span>
          <span style="flex:1" />
          <label class="switch" @click.stop>
            <input type="checkbox" :checked="form[event.event_code]?.enabled"
                   :aria-label="`启用${event.name}通知`"
                   @change="setEnabled(event, $event.target.checked)" />
            <span class="switch-track"><span class="switch-thumb" /></span>
          </label>
        </header>
        <div class="notice-collapse" :class="{ open: openEvents.has(event.event_code) }"
             :inert="openEvents.has(event.event_code) ? null : ''"
             :aria-hidden="!openEvents.has(event.event_code)">
          <div class="notice-event-body">
            <label class="field">
              <span class="field-label">标题模板</span>
              <input v-model="form[event.event_code].title_template" class="input" maxlength="100"
                     placeholder="通知标题" @input="mark(event.event_code)" />
            </label>
            <label class="field">
              <span class="field-label">正文模板</span>
              <textarea v-model="form[event.event_code].content_template" class="textarea notice-textarea"
                        maxlength="1000" rows="4" placeholder="通知正文"
                        @input="mark(event.event_code)" />
            </label>
            <div class="variable-row">
              <span class="auto-label">插入变量</span>
              <button v-for="variable in event.variables" :key="variable" type="button"
                      class="variable-chip" @click="insertVariable(event, variable)">{{ variable }}</button>
            </div>
            <div class="notice-event-actions">
              <button type="button" class="btn btn-sm" @click="resetEvent(event)">恢复默认</button>
              <button type="button" class="btn btn-sm" @click="preview(event)">
                <Icon name="play" :size="13" /> 预览
              </button>
            </div>
            <Transition name="dropdown">
              <div v-if="previews[event.event_code]" class="notice-preview">
                <div class="notice-preview-title">{{ previews[event.event_code].title || '（空标题）' }}</div>
                <pre class="notice-preview-body">{{ previews[event.event_code].content || '（空正文）' }}</pre>
              </div>
            </Transition>
          </div>
        </div>
      </section>
    </div>

    <div v-if="!loading && !visibleEvents.length" class="empty-state">没有匹配的通知事件</div>

    <div v-if="error" class="form-error" role="alert">{{ error }}</div>
  </div>
</template>
