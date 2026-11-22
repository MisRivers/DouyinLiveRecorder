<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api, downloadText } from '../api'
import { toast } from '../store'
import Icon from '../components/Icon.vue'
import Modal from '../components/Modal.vue'

const groups = ref([])
const activeGroup = ref('record')
const values = ref({})
const draft = reactive({})
const initial = reactive({})
const hasValue = reactive({})
const dirty = reactive(new Set())
const loading = ref(true)
const busy = ref(false)
const showAdvanced = ref(false)
const importOpen = ref(false)
const importText = ref('')
const testChannel = ref('钉钉')
const testing = ref(false)
const search = ref('')
const openChannelField = ref('')

const channels = ['微信', '钉钉', '邮箱', 'TG', 'BARK', 'NTFY', 'PUSHPLUS']

const currentGroup = computed(() => groups.value.find((item) => item.code === activeGroup.value))
const fields = computed(() => {
  const list = currentGroup.value?.fields || []
  const needle = search.value.trim().toLowerCase()
  return list.filter((field) => {
    if (!showAdvanced.value && field.advanced) return false
    if (!needle) return true
    return `${field.label} ${field.key} ${field.section}`.toLowerCase().includes(needle)
  })
})
const dirtyCount = computed(() => dirty.size)

function keyOf(field) {
  return `${field.section}::${field.key}`
}

async function load() {
  loading.value = true
  try {
    const [schema, data] = await Promise.all([api('/settings/schema'), api('/settings')])
    groups.value = schema.groups
    if (!groups.value.find((item) => item.code === activeGroup.value) && groups.value.length) {
      activeGroup.value = groups.value[0].code
    }
    const map = {}
    for (const item of data.items) map[`${item.section}::${item.key}`] = item
    values.value = map
    for (const group of groups.value) {
      for (const field of group.fields) {
        const key = keyOf(field)
        const item = map[key]
        const value = field.secret ? '' : (item?.value ?? field.value ?? '')
        draft[key] = value
        initial[key] = value
        hasValue[key] = !!item?.has_value
      }
    }
    dirty.clear()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    loading.value = false
  }
}

function update(field, value) {
  const key = keyOf(field)
  draft[key] = value
  const changed = field.secret ? value !== '' : value !== initial[key]
  if (changed) dirty.add(key)
  else dirty.delete(key)
}

function fieldValue(field) {
  return draft[keyOf(field)] ?? ''
}

function isPushChannelField(field) {
  return field.key === '直播状态推送渠道'
}

function selectedChannels(field) {
  const values = String(fieldValue(field) || '').split(/[,，、\s]+/).filter(Boolean)
  const normalized = values.map((value) => {
    const match = channels.find((channel) => channel.toUpperCase() === value.toUpperCase())
    return match || value
  })
  return [...new Set(normalized)]
}

function toggleChannelMenu(field) {
  const key = keyOf(field)
  openChannelField.value = openChannelField.value === key ? '' : key
}

function closeChannelMenu() {
  openChannelField.value = ''
}

function toggleChannel(field, channel, checked) {
  const selected = new Set(selectedChannels(field))
  if (checked) selected.add(channel)
  else selected.delete(channel)
  update(field, channels.filter((item) => selected.has(item)).join(','))
}

function clearChannels(field) {
  update(field, '')
}

function onDocumentClick(event) {
  if (!event.target.closest('.multi-select')) closeChannelMenu()
}

function onDocumentKeydown(event) {
  if (event.key === 'Escape') closeChannelMenu()
}

function isBool(field) {
  return field.type === 'bool'
}

function boolValue(field) {
  return fieldValue(field) === '是'
}

function setBool(field, checked) {
  update(field, checked ? '是' : '否')
}

function markGroup(code) {
  activeGroup.value = code
  search.value = ''
}

async function save() {
  if (!dirtyCount.value) return
  const updates = []
  for (const group of groups.value) {
    for (const field of group.fields) {
      const key = keyOf(field)
      if (!dirty.has(key)) continue
      const value = draft[key]
      if (field.secret && !value) continue
      updates.push({ section: field.section, key: field.key, value })
    }
  }
  if (!updates.length) { toast('没有需要保存的修改', 'info'); return }
  busy.value = true
  try {
    const result = await api('/settings', { method: 'PUT', body: { updates } })
    const fieldMap = new Map()
    for (const group of groups.value) {
      for (const field of group.fields) fieldMap.set(`${field.section}::${field.key}`, field)
    }
    for (const item of updates) {
      const key = `${item.section}::${item.key}`
      const field = fieldMap.get(key)
      initial[key] = field?.secret ? '' : item.value
      if (field?.secret) {
        draft[key] = ''
        hasValue[key] = !!item.value
      }
      dirty.delete(key)
    }
    toast(`${result.saved} 项配置已保存。${result.effective_hint || ''}`, result.restart_required ? 'warning' : 'success')
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
  }
}

function reset() {
  for (const group of groups.value) {
    for (const field of group.fields) {
      const key = keyOf(field)
      draft[key] = initial[key]
    }
  }
  dirty.clear()
}

async function testPush() {
  testing.value = true
  try {
    const result = await api('/settings/test-push', { method: 'POST', body: { channel: testChannel.value } })
    toast(result.ok ? `${testChannel.value} 测试消息已发送` : `${testChannel.value} 测试失败`, result.ok ? 'success' : 'error')
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    testing.value = false
  }
}

async function exportIni() {
  try {
    const response = await api('/settings/export-ini', { raw: true })
    downloadText('config.ini', await response.text(), 'text/plain;charset=utf-8')
  } catch (err) {
    toast(err.message, 'error')
  }
}

async function importIni() {
  if (!importText.value.trim()) return
  busy.value = true
  try {
    const result = await api('/settings/import-ini', { method: 'POST', body: { content: importText.value } })
    toast(`导入 ${result.imported} 项配置`, 'success')
    importOpen.value = false
    importText.value = ''
    await load()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
  }
}

function beforeUnload(event) {
  if (dirtyCount.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}

onMounted(() => {
  load()
  window.addEventListener('beforeunload', beforeUnload)
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div>
    <div class="sticky-tabs">
      <div class="toolbar">
        <div class="tabs" role="tablist" aria-label="配置分类">
          <button v-for="group in groups" :key="group.code" class="tab" role="tab"
                  :aria-selected="activeGroup === group.code"
                  :class="{ active: activeGroup === group.code }" @click="markGroup(group.code)">
            {{ group.label }}
          </button>
        </div>
        <div style="flex:1" />
        <div class="input-group settings-search" style="max-width:240px;width:100%">
          <span class="prefix"><Icon name="search" :size="14" /></span>
          <input v-model="search" class="input" placeholder="搜索配置项" />
        </div>
        <button class="btn btn-sm" title="导入 ini" aria-label="导入 ini" @click="importOpen = true">
          <Icon name="upload" :size="14" /><span class="desktop-only">导入 ini</span>
        </button>
        <button class="btn btn-sm" title="导出 ini" aria-label="导出 ini" @click="exportIni">
          <Icon name="download" :size="14" /><span class="desktop-only">导出 ini</span>
        </button>
      </div>
    </div>

    <div v-if="loading" class="card settings-panel">
      <div class="skeleton" style="height:18px;width:160px;margin-bottom:18px" />
      <div class="settings-fields">
        <div v-for="n in 6" :key="n" class="field">
          <div class="skeleton" style="height:12px;width:90px" />
          <div class="skeleton" style="height:38px" />
        </div>
      </div>
    </div>

    <template v-else>
      <div v-if="activeGroup === 'push'" class="card settings-panel" style="margin-bottom:16px">
        <div class="toolbar">
          <div>
            <div class="card-title">测试推送</div>
            <div class="card-sub">发送一条“Web 管理端测试消息”，确认渠道配置可用。</div>
          </div>
          <div style="flex:1" />
          <select v-model="testChannel" class="select" style="max-width:160px">
            <option v-for="channel in channels" :key="channel" :value="channel">{{ channel }}</option>
          </select>
          <button class="btn" :disabled="testing" @click="testPush">{{ testing ? '发送中…' : '发送测试' }}</button>
        </div>
      </div>

      <div class="card settings-panel">
        <div class="toolbar" style="margin-bottom:14px">
          <div>
            <div class="card-title">{{ currentGroup?.label }}</div>
            <div class="card-sub">{{ fields.length }} 个可见配置项</div>
          </div>
          <div style="flex:1" />
          <label class="toolbar" style="gap:8px;font-size:12px;color:var(--text-secondary)">
            <span class="switch">
              <input v-model="showAdvanced" type="checkbox" />
              <span class="switch-track"><span class="switch-thumb" /></span>
            </span>
            显示高级项
          </label>
        </div>

        <div class="settings-fields">
          <div v-for="field in fields" :key="field.section + field.key" class="field"
               :class="{ 'span-2': field.type === 'multiline' }">
            <div class="toolbar" style="gap:8px">
              <label class="field-label">{{ field.label }}</label>
              <span v-if="field.source === 'upstream_new'" class="badge warning">上游新增</span>
              <span v-if="hasValue[field.section + '::' + field.key] && field.secret" class="badge success">已设置</span>
            </div>

            <div v-if="isPushChannelField(field)" class="multi-select">
              <button type="button" class="multi-select-trigger"
                      :aria-expanded="openChannelField === keyOf(field)"
                      aria-haspopup="true"
                      @click.stop="toggleChannelMenu(field)">
                <span v-if="selectedChannels(field).length" class="multi-select-chips">
                  <span v-for="channel in selectedChannels(field)" :key="channel" class="channel-chip">{{ channel }}</span>
                </span>
                <span v-else class="multi-select-placeholder">请选择推送渠道</span>
                <Icon class="multi-select-chevron" name="down" :size="14" />
              </button>
              <Transition name="dropdown">
                <div v-if="openChannelField === keyOf(field)" class="multi-select-menu"
                     role="group" aria-label="选择直播状态推送渠道" @click.stop>
                  <label v-for="channel in channels" :key="channel" class="multi-select-option">
                    <input type="checkbox" :checked="selectedChannels(field).includes(channel)"
                           @change="toggleChannel(field, channel, $event.target.checked)" />
                    <span>{{ channel }}</span>
                  </label>
                  <div class="multi-select-actions">
                    <button type="button" class="btn btn-sm" @click="clearChannels(field)">清空</button>
                    <button type="button" class="btn btn-sm btn-primary" @click="closeChannelMenu">完成</button>
                  </div>
                </div>
              </Transition>
            </div>

            <label v-else-if="isBool(field)" class="switch" style="margin-top:2px">
              <input type="checkbox" :checked="boolValue(field)" @change="setBool(field, $event.target.checked)" />
              <span class="switch-track"><span class="switch-thumb" /></span>
            </label>

            <select v-else-if="field.type === 'enum'" class="select" :value="fieldValue(field)"
                    @change="update(field, $event.target.value)">
              <option v-for="option in field.options || []" :key="option" :value="option">{{ option }}</option>
            </select>

            <textarea v-else-if="field.type === 'multiline'" class="textarea" :value="fieldValue(field)"
                      :placeholder="field.secret ? '已设置，留空表示不修改' : ''"
                      @input="update(field, $event.target.value)" />

            <input v-else-if="field.type === 'secret'" class="input" type="password" :value="fieldValue(field)"
                   :placeholder="hasValue[field.section + '::' + field.key] ? '已设置，留空表示不修改' : '未设置'"
                   autocomplete="new-password" @input="update(field, $event.target.value)" />

            <input v-else-if="field.type === 'int' || field.type === 'float'" class="input" type="number"
                   :step="field.type === 'float' ? '0.1' : '1'" :value="fieldValue(field)"
                   @input="update(field, $event.target.value)" />

            <input v-else class="input" :value="fieldValue(field)" @input="update(field, $event.target.value)" />

            <span v-if="field.description" class="field-hint">{{ field.description }}</span>
            <span v-else-if="field.secret" class="field-hint">敏感值不会回显，留空表示保持原值。</span>
          </div>
        </div>

        <div v-if="!fields.length" class="empty-state">没有匹配的配置项</div>
      </div>

      <div class="save-bar">
        <span class="dirty-count">{{ dirtyCount ? `${dirtyCount} 项未保存` : '所有修改已保存' }}</span>
        <div style="flex:1" />
        <button class="btn" :disabled="!dirtyCount || busy" @click="reset">重置</button>
        <button class="btn btn-primary" :disabled="!dirtyCount || busy" @click="save">
          {{ busy ? '保存中…' : '保存配置' }}
        </button>
      </div>
    </template>

    <Modal :open="importOpen" title="导入 config.ini" wide @close="importOpen = false">
      <p class="field-hint" style="margin-bottom:10px">
        导入会覆盖同名配置项；上游新增的键会自动加入“上游新增”标记。建议先导出一份备份。
      </p>
      <textarea v-model="importText" class="textarea" style="min-height:260px"
                placeholder="[录制设置]&#10;视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频 = ts" />
      <template #footer>
        <button class="btn" @click="importOpen = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="importIni">{{ busy ? '导入中…' : '导入' }}</button>
      </template>
    </Modal>
  </div>
</template>
