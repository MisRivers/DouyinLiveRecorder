<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, downloadText } from '../api'
import { formatTime, store, toast } from '../store'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Modal from '../components/Modal.vue'
import Icon from '../components/Icon.vue'
import ScheduleEditor from '../components/ScheduleEditor.vue'

const QUALITIES = ['原画', '蓝光', '超清', '高清', '标清', '流畅']
const PAGE_SIZES = [10, 20, 30, 50, 100]
const rooms = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(readPageSize())
const platforms = ref([])
const loading = ref(false)
const query = ref('')
const platformFilter = ref('')
const busy = ref(false)
const modalOpen = ref(false)
const editing = ref(null)
const formError = ref('')
const importOpen = ref(false)
const importText = ref('')
const confirmDisable = ref(null)
const confirmDelete = ref(null)
const scheduleOpen = ref(false)
const scheduleRoom = ref(null)
const draftScheduleOpen = ref(false)
const draftSchedule = ref([])
const platformIdInput = ref(null)
const roomUrlInput = ref(null)
const route = useRoute()
const highlightRoomId = ref(null)
const focusNotice = ref(null)
const fabBottom = ref(144)
const fabDragging = ref(false)
let highlightTimer = null
let fabDrag = null
let fabMoved = false
const FAB_MIN_BOTTOM = 96
const FAB_STORAGE_KEY = 'dlr.rooms.fabBottom'

function readFabBottom() {
  try {
    const value = Number(localStorage.getItem(FAB_STORAGE_KEY))
    return Number.isFinite(value) ? value : 144
  } catch {
    return 144
  }
}

function clampFab(value) {
  const max = Math.max(FAB_MIN_BOTTOM, window.innerHeight - 220)
  return Math.min(Math.max(value, FAB_MIN_BOTTOM), max)
}

function persistFab() {
  try {
    localStorage.setItem(FAB_STORAGE_KEY, String(Math.round(fabBottom.value)))
  } catch { /* storage may be unavailable */ }
}

function onFabPointerDown(event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return
  fabDrag = { startY: event.clientY, startBottom: fabBottom.value }
  fabMoved = false
  fabDragging.value = true
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function onFabPointerMove(event) {
  if (!fabDrag) return
  const delta = fabDrag.startY - event.clientY
  if (Math.abs(delta) > 3) fabMoved = true
  fabBottom.value = clampFab(fabDrag.startBottom + delta)
}

function endFabDrag() {
  if (!fabDrag) return
  fabDrag = null
  fabDragging.value = false
  persistFab()
}

function onFabClick() {
  if (fabMoved) {
    fabMoved = false
    return
  }
  openCreate()
}

function onResize() {
  fabBottom.value = clampFab(fabBottom.value)
}

const form = reactive({
  platform_code: 'douyin',
  mode: 'id',
  platform_id: '',
  url: '',
  quality: '原画',
  custom_name: '',
  enabled: true
})

const selectedPlatform = computed(() => platforms.value.find((item) => item.code === form.platform_code))
const enabledPlatforms = computed(() => platforms.value.filter((item) => item.enabled))
const formPlatforms = computed(() => platforms.value.filter((item) =>
  item.enabled || item.code === editing.value?.platform_code))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

function readPageSize() {
  try {
    const saved = Number(localStorage.getItem('dlr.rooms.pageSize') || 10)
    return PAGE_SIZES.includes(saved) ? saved : 10
  } catch {
    return 10
  }
}

function persistPageSize(value) {
  try {
    localStorage.setItem('dlr.rooms.pageSize', String(value))
  } catch { /* storage may be unavailable */ }
}
const prefix = computed(() => {
  const template = selectedPlatform.value?.url_template
  return template && template.includes('{id}') ? template.split('{id}')[0] : ''
})
const generatedUrl = computed(() => {
  const template = selectedPlatform.value?.url_template
  if (form.mode === 'id' && template && form.platform_id) return template.replace('{id}', form.platform_id)
  return form.url
})
const canQuick = computed(() => selectedPlatform.value?.quick_add_mode === 'id' && !!selectedPlatform.value?.url_template)
const draftScheduleText = computed(() => {
  const list = draftSchedule.value
  if (!list.length) return '全天（无计划）'
  const first = list[0]
  const days = first.weekdays.length === 7 ? '每天' : `${first.weekdays.length} 天`
  return `${days} ${first.start}-${first.end}${list.length > 1 ? ` 等 ${list.length} 段` : ''}`
})

async function loadPlatforms() {
  try {
    const data = await api('/platforms?include_disabled=1')
    const preferred = ['douyin', 'kuaishou', 'huya', 'douyu', 'bilibili', 'tiktok', 'youtube', 'twitch', 'sooplive', 'chzzk']
    platforms.value = [...data].sort((a, b) => {
      if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
      const ia = preferred.indexOf(a.code)
      const ib = preferred.indexOf(b.code)
      if (ia !== -1 || ib !== -1) {
        if (ia === -1) return 1
        if (ib === -1) return -1
        return ia - ib
      }
      return a.name.localeCompare(b.name, 'zh-CN')
    })
    if (!platforms.value.find((item) => item.code === form.platform_code && item.enabled) && enabledPlatforms.value.length) {
      form.platform_code = defaultPlatform()
    }
  } catch (err) {
    toast(err.message, 'error')
  }
}

function defaultPlatform() {
  return enabledPlatforms.value.find((item) => item.code === 'douyin')?.code
    || enabledPlatforms.value[0]?.code
    || platforms.value.find((item) => item.code === 'douyin')?.code
    || platforms.value[0]?.code
    || 'douyin'
}

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(page.value), page_size: String(pageSize.value), sort: 'sort_order', order: 'asc'
    })
    if (query.value.trim()) params.set('query', query.value.trim())
    if (platformFilter.value) params.set('platform_code', platformFilter.value)
    const data = await api(`/rooms?${params}`)
    rooms.value = data.items
    total.value = data.total
    if (page.value > pageCount.value) {
      page.value = pageCount.value
      await load()
    }
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.platform_code = defaultPlatform()
  const platform = platforms.value.find((item) => item.code === form.platform_code)
  form.mode = platform?.quick_add_mode === 'id' && platform?.url_template ? 'id' : 'full_url'
  form.platform_id = ''
  form.url = ''
  form.quality = '原画'
  form.custom_name = ''
  form.enabled = true
  formError.value = ''
}

watch(() => form.platform_code, () => {
  if (editing.value) return
  if (!canQuick.value && form.mode === 'id') form.mode = 'full_url'
  if (canQuick.value && !form.platform_id && form.mode === 'full_url') form.mode = 'id'
})

function openCreate() {
  if (!enabledPlatforms.value.length) {
    toast('所有平台均已禁用，请先在“系统配置 · 平台管理”启用平台', 'warning')
    return
  }
  editing.value = null
  draftSchedule.value = []
  resetForm()
  modalOpen.value = true
  setTimeout(() => {
    const input = form.mode === 'id' ? platformIdInput.value : roomUrlInput.value
    input?.focus()
  }, 90)
}

function openSchedule(room) {
  scheduleRoom.value = room
  scheduleOpen.value = true
}

async function onScheduleSaved() {
  await load()
}

function onDraftScheduleSaved(windows) {
  draftSchedule.value = windows
  draftScheduleOpen.value = false
}

function openEdit(room) {
  editing.value = room
  form.platform_code = room.platform_code
  form.mode = 'full_url'
  form.platform_id = ''
  form.url = room.url
  form.quality = room.quality
  form.custom_name = room.custom_name || ''
  form.enabled = room.enabled
  formError.value = ''
  modalOpen.value = true
}

async function save() {
  formError.value = ''
  if (!form.platform_code) { formError.value = '请选择平台'; return }
  if (form.mode === 'id' && !form.platform_id.trim()) { formError.value = '请输入平台 ID 或主播号'; return }
  if (form.mode === 'full_url' && !form.url.trim()) { formError.value = '请输入完整直播间地址'; return }
  busy.value = true
  try {
    if (editing.value) {
      const payload = {
        platform_code: form.platform_code,
        url: form.mode === 'id' ? generatedUrl.value : form.url,
        quality: form.quality,
        custom_name: form.custom_name || null,
        enabled: form.enabled
      }
      await api(`/rooms/${editing.value.id}`, { method: 'PATCH', body: payload })
      toast('直播间已更新', 'success')
    } else {
      const payload = {
        platform_code: form.platform_code,
        quality: form.quality,
        custom_name: form.custom_name || null,
        enabled: form.enabled
      }
      let created
      if (form.mode === 'id') {
        payload.platform_id = form.platform_id.trim()
        created = await api('/rooms/quick-add', { method: 'POST', body: payload })
      } else {
        payload.url = form.url.trim()
        created = await api('/rooms', { method: 'POST', body: payload })
      }
      if (draftSchedule.value.length && created?.id) {
        try {
          await api(`/rooms/${created.id}/schedule`, {
            method: 'PUT',
            body: { windows: draftSchedule.value }
          })
        } catch (err) {
          toast(`直播间已添加，但计划保存失败：${err.message}`, 'warning')
        }
      }
      toast('直播间已添加', 'success')
    }
    modalOpen.value = false
    await load()
  } catch (err) {
    formError.value = err.message
  } finally {
    busy.value = false
  }
}

async function toggle(room, value) {
  if (!value && room.live_state === 'recording') {
    confirmDisable.value = room
    return
  }
  await setEnabled(room, value)
}

async function setEnabled(room, value) {
  busy.value = true
  try {
    await api(`/rooms/${room.id}`, { method: 'PATCH', body: { enabled: value } })
    room.enabled = value
    toast(value ? '已启用' : '已停用', 'success')
    await load()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
    confirmDisable.value = null
  }
}

async function remove(room) {
  busy.value = true
  try {
    await api(`/rooms/${room.id}`, { method: 'DELETE' })
    confirmDelete.value = null
    toast('直播间已删除', 'success')
    if (rooms.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
  }
}

async function exportRooms() {
  try {
    const response = await api('/rooms/export', { raw: true })
    downloadText('URL_config.ini', await response.text(), 'text/plain;charset=utf-8')
  } catch (err) {
    toast(err.message, 'error')
  }
}

async function importRooms() {
  if (!importText.value.trim()) return
  busy.value = true
  try {
    const result = await api('/rooms/import', { method: 'POST', body: { content: importText.value } })
    toast(`导入 ${result.imported} 个，跳过 ${result.skipped} 个`, 'success')
    importOpen.value = false
    importText.value = ''
    await load()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
  }
}

function applyFilter() {
  focusNotice.value = null
  page.value = 1
  load()
}

function changePage(delta) {
  const next = Math.min(pageCount.value, Math.max(1, page.value + delta))
  if (next === page.value) return
  focusNotice.value = null
  page.value = next
  load()
}

watch(pageSize, (value) => {
  persistPageSize(value)
}, { flush: 'post' })

function changePageSize() {
  focusNotice.value = null
  page.value = 1
  load()
}

async function findRoomIndex(roomId) {
  let currentPage = 1
  let offset = 0
  while (true) {
    const data = await api(`/rooms?page=${currentPage}&page_size=200&sort=sort_order&order=asc`)
    const index = data.items.findIndex((room) => room.id === roomId)
    if (index >= 0) return offset + index
    if (!data.items.length || offset + data.items.length >= data.total) return -1
    offset += data.items.length
    currentPage += 1
  }
}

async function focusRoom(roomId) {
  query.value = ''
  platformFilter.value = ''
  if (highlightTimer) {
    clearTimeout(highlightTimer)
    highlightTimer = null
  }
  highlightRoomId.value = null
  focusNotice.value = null
  let index
  try {
    index = await findRoomIndex(roomId)
  } catch (err) {
    toast(err.message, 'error')
    await load()
    return
  }
  if (index < 0) {
    toast('未找到该直播间，可能已被删除', 'warning')
    await load()
    return
  }
  page.value = Math.floor(index / pageSize.value) + 1
  await load()
  await nextTick()
  const row = document.querySelector(`.rooms-table tbody tr[data-room-id="${roomId}"]`)
  if (!row) return
  const target = rooms.value.find((room) => room.id === roomId)
  const targetName = target?.custom_name || target?.last_anchor_name || '该主播'
  row.scrollIntoView({ behavior: 'smooth', block: 'center' })
  await new Promise((resolve) => setTimeout(resolve, 240))
  if (highlightTimer) clearTimeout(highlightTimer)
  highlightRoomId.value = roomId
  focusNotice.value = {
    name: targetName,
    page: page.value,
    pageCount: pageCount.value,
    total: total.value
  }
  if (window.innerWidth <= 760) {
    toast(`已定位到「${targetName}」 · 第 ${page.value} / ${pageCount.value} 页 · 共 ${total.value} 个`, 'info', 3600)
  }
  highlightTimer = setTimeout(() => {
    highlightRoomId.value = null
    focusNotice.value = null
    highlightTimer = null
  }, 3200)
}

function stateText(state) {
  return {
    recording: '录制中', live: '直播中', waiting: '等待直播', checking: '检测中',
    stopping: '停止中', error: '异常', disabled: '已停用',
    scheduled: '计划外', platform_disabled: '平台已禁用'
  }[state] || state
}

function stateClass(state) {
  if (state === 'recording') return 'recording'
  if (state === 'error' || state === 'platform_disabled') return 'error'
  if (state === 'scheduled') return 'scheduled'
  if (['live', 'waiting', 'checking', 'stopping'].includes(state)) return 'waiting'
  return 'disabled'
}

watch(() => route.query.focus, (value) => {
  const focusId = Number(value)
  if (Number.isInteger(focusId) && focusId > 0) focusRoom(focusId)
})

onMounted(async () => {
  fabBottom.value = clampFab(readFabBottom())
  window.addEventListener('resize', onResize)
  await loadPlatforms()
  const focusId = Number(route.query.focus)
  if (Number.isInteger(focusId) && focusId > 0) await focusRoom(focusId)
  else await load()
})

onBeforeUnmount(() => {
  if (highlightTimer) clearTimeout(highlightTimer)
  highlightTimer = null
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div class="rooms-page">
    <div class="rooms-toolbar">
      <button class="btn btn-primary desktop-only" @click="openCreate"><Icon name="plus" :size="16" /> 新增直播间</button>
      <div class="input-group rooms-search" style="max-width:280px;width:100%">
        <span class="prefix"><Icon name="search" :size="14" /></span>
        <input v-model="query" class="input" placeholder="搜索主播、地址" @keyup.enter="applyFilter" />
      </div>
      <button class="btn btn-icon btn-sm mobile-only rooms-refresh" title="刷新" aria-label="刷新" @click="load">
        <Icon name="refresh" :size="15" />
      </button>
      <select v-model="platformFilter" class="select rooms-filter" style="max-width:160px" @change="applyFilter">
        <option value="">全部平台</option>
        <option v-for="item in platforms" :key="item.code" :value="item.code">{{ item.name }}</option>
      </select>
      <div class="toolbar desktop-only" style="gap:8px;margin-left:auto">
        <button class="btn btn-sm" @click="importOpen = true"><Icon name="upload" :size="14" /> 导入</button>
        <button class="btn btn-sm" @click="exportRooms"><Icon name="download" :size="14" /> 导出</button>
        <button class="btn btn-sm" @click="load"><Icon name="refresh" :size="14" /> 刷新</button>
      </div>
      <div class="toolbar mobile-only mobile-actions" style="gap:6px">
        <button class="btn btn-icon btn-sm" title="导入" aria-label="导入" @click="importOpen = true"><Icon name="upload" :size="15" /></button>
        <button class="btn btn-icon btn-sm" title="导出" aria-label="导出" @click="exportRooms"><Icon name="download" :size="15" /></button>
      </div>
    </div>
    <button class="fab" :class="{ dragging: fabDragging }" :style="{ bottom: `${fabBottom}px` }"
            title="新增直播间（可沿右侧拖动）" aria-label="新增直播间，可沿右侧拖动"
            @pointerdown="onFabPointerDown" @pointermove="onFabPointerMove"
            @pointerup="endFabDrag" @pointercancel="endFabDrag" @click="onFabClick">
      <Icon name="plus" :size="24" />
    </button>

    <div v-if="focusNotice" class="focus-notice" role="status" aria-live="polite">
      <span class="focus-notice-dot" />
      已定位到「{{ focusNotice.name }}」 · 第 {{ focusNotice.page }} / {{ focusNotice.pageCount }} 页 · 共 {{ focusNotice.total }} 个
    </div>

    <div class="table-wrap">
      <div class="rooms-scroll">
        <table class="data-table rooms-table">
          <thead>
            <tr>
              <th style="width:76px">序号</th>
              <th style="width:112px">启用</th>
              <th>自定义主播名</th>
              <th>URL</th>
              <th style="width:96px">画质</th>
              <th style="width:214px;text-align:right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(room, index) in rooms" :key="room.id"
                :data-room-id="room.id"
                :class="{ 'room-focus': highlightRoomId === room.id }">
              <td data-label="序号">
                <span class="order-number">{{ (page - 1) * pageSize + index + 1 }}</span>
              </td>
              <td data-label="启用">
                <div class="enable-cell">
                  <label class="switch">
                    <input type="checkbox" :checked="room.enabled" :disabled="busy"
                           :aria-label="room.enabled ? '停用直播间' : '启用直播间'"
                           @change="toggle(room, $event.target.checked)" />
                    <span class="switch-track"><span class="switch-thumb" /></span>
                  </label>
                  <span class="cell-muted">{{ room.enabled ? '已启用' : '已停用' }}</span>
                </div>
              </td>
              <td data-label="自定义主播名">
                <div class="room-name-line">
                  <span class="room-name-text">{{ room.custom_name || room.last_anchor_name || '未设置' }}</span>
                  <span v-if="['recording', 'error', 'platform_disabled', 'scheduled'].includes(room.live_state)"
                        class="badge" :class="stateClass(room.live_state)">{{ stateText(room.live_state) }}</span>
                  <button type="button" class="schedule-chip" :title="`录制计划：${room.schedule_summary}`"
                          @click.stop="openSchedule(room)">
                    <Icon name="calendar" :size="13" />
                    <span>{{ room.schedule_summary }}</span>
                  </button>
                  <span v-if="highlightRoomId === room.id" class="badge locating">已定位</span>
                </div>
                <div class="cell-muted">
                  {{ room.platform_name }}<span class="rooms-mobile-quality"> · {{ room.quality }}</span>
                  <span v-if="room.platform_enabled === false" class="badge warning platform-off-badge">平台已禁用</span>
                </div>
              </td>
              <td data-label="URL" class="cell-url">
                <div class="url-cell" :title="room.url">{{ room.url }}</div>
              </td>
              <td data-label="画质">{{ room.quality }}</td>
              <td data-label="操作" class="cell-actions">
                <div class="cell-actions-inner">
                  <button class="btn btn-sm btn-ghost room-action-btn" title="录制计划" aria-label="录制计划"
                          @click="openSchedule(room)">
                    <Icon name="calendar" :size="14" /><span class="room-action-label">计划</span>
                  </button>
                  <button class="btn btn-sm btn-ghost room-action-btn" title="编辑直播间" aria-label="编辑直播间"
                          @click="openEdit(room)">
                    <Icon name="edit" :size="14" /><span class="room-action-label">编辑</span>
                  </button>
                  <button class="btn btn-sm btn-ghost room-action-btn" style="color:var(--danger)"
                          title="删除直播间" aria-label="删除直播间" @click="confirmDelete = room">
                    <Icon name="trash" :size="14" /><span class="room-action-label">删除</span>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!loading && !rooms.length" class="rooms-empty-row">
              <td colspan="6" class="table-empty">还没有直播间，点击“新增直播间”开始</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="toolbar pagination-bar">
      <span class="cell-muted">共 {{ total }} 个</span>
      <select v-model.number="pageSize" class="select compact" aria-label="每页条数"
              @change="changePageSize">
        <option v-for="size in PAGE_SIZES" :key="size" :value="size">{{ size }} 条/页</option>
      </select>
      <button class="btn btn-sm" :disabled="page <= 1" @click="changePage(-1)">上一页</button>
      <span class="cell-muted">第 {{ page }} / {{ pageCount }} 页</span>
      <button class="btn btn-sm" :disabled="page >= pageCount" @click="changePage(1)">下一页</button>
    </div>

    <Modal :open="modalOpen" :title="editing ? '编辑直播间' : '新增直播间'" wide @close="modalOpen = false">
      <div class="form-grid">
        <div class="field span-2 room-basic-row">
          <div class="field">
            <label class="field-label">平台</label>
            <select v-model="form.platform_code" class="select">
              <option v-for="item in formPlatforms" :key="item.code" :value="item.code">
                {{ item.name }}{{ item.enabled ? '' : '（已禁用）' }}
              </option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">画质</label>
            <select v-model="form.quality" class="select">
              <option v-for="item in QUALITIES" :key="item" :value="item">{{ item }}</option>
            </select>
          </div>
          <div class="field">
            <label class="field-label">自定义主播名（可选）</label>
            <input v-model="form.custom_name" class="input" placeholder="留空则使用平台主播名" />
            <span class="field-hint">不能包含逗号、# 或换行。</span>
          </div>
        </div>
        <div class="field span-2">
          <label class="field-label">直播间地址</label>
          <div class="tabs" style="align-self:flex-start;margin-bottom:6px">
            <button class="tab" :class="{ active: form.mode === 'id' }" :disabled="!canQuick"
                    @click="form.mode = 'id'">快速填充</button>
            <button class="tab" :class="{ active: form.mode === 'full_url' }" @click="form.mode = 'full_url'">完整链接</button>
          </div>
          <div v-if="form.mode === 'id'" class="input-group">
            <span class="prefix">{{ prefix }}</span>
            <input ref="platformIdInput" v-model="form.platform_id" class="input"
                   :placeholder="selectedPlatform?.example ? '例如 ' + selectedPlatform.name + ' ID' : '请输入平台 ID'" />
          </div>
          <input v-else ref="roomUrlInput" v-model="form.url" class="input" placeholder="请输入完整的直播间地址" />
          <div v-if="generatedUrl" class="quick-preview">生成地址：{{ generatedUrl }}</div>
          <span class="field-hint">{{ selectedPlatform?.example ? '示例：' + selectedPlatform.example : '' }}</span>
        </div>
        <div v-if="!editing" class="field span-2">
          <label class="field-label">录制计划（可选）</label>
          <div class="schedule-draft-row">
            <button type="button" class="schedule-chip" title="点击设置录制计划"
                    @click="draftScheduleOpen = true">
              <Icon name="calendar" :size="13" />
              <span>{{ draftScheduleText }}</span>
            </button>
            <button v-if="draftSchedule.length" type="button" class="btn btn-sm btn-ghost"
                    @click="draftSchedule = []">清除</button>
          </div>
          <span class="field-hint">默认全天录制；点击上方计划可设置每周时段，保存直播间后生效。</span>
        </div>
        <div class="field">
          <label class="field-label">启用</label>
          <label class="switch" style="margin-top:4px">
            <input v-model="form.enabled" type="checkbox" />
            <span class="switch-track"><span class="switch-thumb" /></span>
          </label>
        </div>
        <div v-if="formError" class="form-error span-2">{{ formError }}</div>
      </div>
      <template #footer>
        <button class="btn" @click="modalOpen = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="save">{{ busy ? '保存中…' : '保存' }}</button>
      </template>
    </Modal>

    <Modal :open="importOpen" title="导入直播间" wide @close="importOpen = false">
      <p class="field-hint" style="margin-bottom:10px">
        支持原程序 URL_config.ini 格式：每行一个地址，行首 # 表示停用，可用“画质,URL”或“URL,主播: 名称”。
      </p>
      <textarea v-model="importText" class="textarea" style="min-height:220px"
                placeholder="https://live.douyin.com/745964462470&#10;超清,https://live.bilibili.com/21593109&#10;#https://www.huya.com/116,主播: 测试" />
      <template #footer>
        <button class="btn" @click="importOpen = false">取消</button>
        <button class="btn btn-primary" :disabled="busy" @click="importRooms">{{ busy ? '导入中…' : '导入' }}</button>
      </template>
    </Modal>

    <ConfirmDialog
      :open="!!confirmDisable"
      title="停用正在录制的直播间"
      :message="`停用“${confirmDisable?.custom_name || confirmDisable?.last_anchor_name || confirmDisable?.url}”会优雅结束当前录制，并把 TS 文件加入转码队列。确定继续？`"
      confirm-text="停用并结束录制"
      :busy="busy"
      @confirm="setEnabled(confirmDisable, false)"
      @cancel="confirmDisable = null; load()"
    />

    <ConfirmDialog
      :open="!!confirmDelete"
      title="删除直播间"
      :message="`确定删除“${confirmDelete?.custom_name || confirmDelete?.last_anchor_name || confirmDelete?.url}”吗？已录制的文件不会被删除。`"
      confirm-text="删除"
      danger
      :busy="busy"
      @confirm="remove(confirmDelete)"
      @cancel="confirmDelete = null"
    />

    <ScheduleEditor
      :open="scheduleOpen"
      :room="scheduleRoom"
      @close="scheduleOpen = false"
      @saved="onScheduleSaved"
    />

    <ScheduleEditor
      :open="draftScheduleOpen"
      draft
      :initial-windows="draftSchedule"
      @close="draftScheduleOpen = false"
      @saved="onDraftScheduleSaved"
    />
  </div>
</template>
