<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import {
  formatBytes, formatDuration, formatTime, refreshSnapshot, store, toast
} from '../store'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Icon from '../components/Icon.vue'

const now = ref(Date.now())
const search = ref('')
const busy = ref(false)
const confirmDisable = ref(null)
let timer = null

const stateLabels = {
  disabled: '已停用',
  checking: '检测中',
  waiting: '等待直播',
  live: '直播中',
  recording: '录制中',
  stopping: '停止中',
  error: '异常',
  stopped: '未启动',
  starting: '启动中',
  running: '运行中'
}

const recorderState = computed(() => store.recorder?.state || 'stopped')
const ffmpegMissing = computed(() => store.recorder && !store.recorder.ffmpeg_path)
const heartbeatStale = computed(() => {
  now.value
  const value = store.recorder?.heartbeat_at
  if (!value || !['running', 'starting', 'stopping'].includes(recorderState.value)) return false
  return Date.now() - new Date(value).getTime() > 15000
})

const filteredWaiting = computed(() => {
  const items = store.waiting?.items || []
  const needle = search.value.trim().toLowerCase()
  if (!needle) return items
  return items.filter((item) => {
    const text = `${item.anchor_display || ''} ${item.anchor_name || ''} ${item.url || ''} ${item.platform_name || ''}`.toLowerCase()
    return text.includes(needle)
  })
})

function elapsed(item) {
  if (!item.started_at) return '00:00:00'
  const start = new Date(item.started_at).getTime()
  return formatDuration((now.value - start) / 1000)
}

function startedAt(item) {
  if (!item.started_at) return '—'
  const value = new Date(item.started_at)
  if (Number.isNaN(value.getTime())) return formatTime(item.started_at)
  const pad = (part) => String(part).padStart(2, '0')
  return `${pad(value.getMonth() + 1)}-${pad(value.getDate())} ${pad(value.getHours())}:${pad(value.getMinutes())}:${pad(value.getSeconds())}`
}

function stateClass(state) {
  if (state === 'recording') return 'recording'
  if (state === 'error') return 'error'
  if (['waiting', 'checking', 'live', 'stopping'].includes(state)) return 'waiting'
  return 'disabled'
}

async function refresh() {
  try { await refreshSnapshot() } catch (err) { toast(err.message, 'error') }
}

function toggleRecording(item, checked) {
  if (checked) return
  confirmDisable.value = item
}

async function disableRecording() {
  const item = confirmDisable.value
  if (!item) return
  busy.value = true
  try {
    await api(`/rooms/${item.room_id}`, { method: 'PATCH', body: { enabled: false } })
    toast('已请求停用，录制收尾后将自动转 MP4', 'success')
    confirmDisable.value = null
    await refresh()
  } catch (err) {
    toast(err.message, 'error')
    confirmDisable.value = null
    await refresh()
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  refresh()
  timer = window.setInterval(() => { now.value = Date.now() }, 1000)
})
onBeforeUnmount(() => { if (timer) window.clearInterval(timer) })
</script>

<template>
  <div>
    <div v-if="ffmpegMissing" class="card" style="border-color:#fde68a;background:var(--warning-soft);margin-bottom:16px">
      <div class="card-body" style="display:flex;gap:10px;align-items:center;color:var(--warning)">
        <Icon name="alert" :size="18" />
        <span>未找到 ffmpeg。请将 ffmpeg 放在程序目录的 ffmpeg/ffmpeg.exe，或安装到系统 PATH 后再启动录制。</span>
      </div>
    </div>
    <div v-if="heartbeatStale" class="card" style="border-color:#fecaca;background:var(--danger-soft);margin-bottom:16px">
      <div class="card-body" style="display:flex;gap:10px;align-items:center;color:var(--danger)">
        <Icon name="alert" :size="18" />
        <span>录制服务心跳异常，可能已停止响应。已录制的文件会保留，可尝试重启录制引擎恢复。</span>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card primary">
        <div class="stat-label"><span v-if="(store.summary?.recording || 0) > 0" class="rec-dot" />正在录制</div>
        <div class="stat-value">{{ store.summary?.recording || 0 }}</div>
        <div class="stat-note">个直播间</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">等待直播</div>
        <div class="stat-value">{{ store.summary?.waiting || 0 }}</div>
        <div class="stat-note">检测中与未开播</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">启用直播间</div>
        <div class="stat-value">{{ store.summary?.enabled || 0 }}</div>
        <div class="stat-note">共 {{ store.summary?.total || 0 }} 个</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">录制程序</div>
        <div class="stat-value" style="font-size:20px">{{ stateLabels[recorderState] || recorderState }}</div>
        <div class="stat-note">{{ store.recorder?.ffmpeg_version ? 'ffmpeg 已就绪' : '等待环境检查' }}</div>
      </div>
    </div>

    <section class="live-section">
      <div class="toolbar" style="margin-bottom:12px">
        <div>
          <h2 style="font-size:16px;font-weight:600">正在录制</h2>
          <div class="card-sub">录制中的直播间会实时更新时长与文件大小。</div>
        </div>
        <div style="flex:1" />
        <button class="btn btn-sm" @click="refresh"><Icon name="refresh" :size="14" /> 刷新</button>
      </div>
      <div v-if="store.recordings?.length" class="record-grid">
        <article v-for="item in store.recordings" :key="item.room_id" class="card record-card">
          <div class="record-head">
            <div>
              <div class="record-name">{{ item.anchor_display || item.anchor_name || '未知主播' }}</div>
              <div class="record-meta">
                <span>{{ item.platform_name }}</span>
                <span>{{ item.quality }}</span>
                <span v-if="item.title">{{ item.title }}</span>
              </div>
            </div>
            <div class="record-head-badges">
              <span v-if="item.error_code === 'RECONNECTING'" class="badge warning">
                <span class="state-dot" style="background:var(--warning)" />重连中
              </span>
              <span class="badge recording"><span class="state-dot" style="background:var(--recording)" />录制中</span>
            </div>
          </div>
          <div v-if="item.error_code === 'RECONNECTING'" class="record-reconnect">
            <Icon name="alert" :size="13" />
            <span>直播信号中断，正在自动重连；30 秒内恢复会继续本次录制。</span>
          </div>
          <div class="record-metrics">
            <div class="record-metric">
              <div class="label">已录制</div>
              <div class="value">{{ elapsed(item) }}</div>
            </div>
            <div class="record-metric">
              <div class="label">文件大小</div>
              <div class="value">{{ formatBytes(item.bytes_written) }}</div>
            </div>
            <div class="record-metric">
              <div class="label">开始时间</div>
              <div class="value metric-time" :title="formatTime(item.started_at)">{{ startedAt(item) }}</div>
            </div>
          </div>
          <div v-if="item.file_path" class="record-path" :title="item.file_path">{{ item.file_path }}</div>
          <div class="record-actions">
            <div class="record-enable">
              <span class="cell-muted">启用</span>
              <label class="switch">
                <input type="checkbox" :checked="item.enabled !== false"
                       :aria-label="item.enabled !== false ? '停用该直播间' : '启用该直播间'"
                       @change="toggleRecording(item, $event.target.checked)" />
                <span class="switch-track"><span class="switch-thumb" /></span>
              </label>
            </div>
            <div style="flex:1" />
            <RouterLink :to="{ path: '/rooms', query: { focus: item.room_id } }" class="btn btn-sm">前往直播间管理</RouterLink>
          </div>
        </article>
      </div>
      <div v-else class="card empty-state">
        <div class="empty-icon"><Icon name="live" :size="22" /></div>
        <div>当前没有正在录制的直播间</div>
        <div class="field-hint" style="margin-top:6px">使用顶部录制控制启动后，开播的直播间会出现在这里。</div>
      </div>
    </section>

    <section class="live-section">
      <div class="toolbar waiting-toolbar" style="margin-bottom:12px">
        <div class="waiting-heading">
          <h2 style="font-size:16px;font-weight:600">待开播监控</h2>
          <div class="card-sub">只读视图，仅显示已启用且未在录制的直播间。增删改请前往直播间管理。</div>
        </div>
        <RouterLink to="/rooms" class="btn btn-sm waiting-link">前往直播间管理</RouterLink>
        <div class="field waiting-search" style="max-width:260px;width:100%">
          <div class="input-group">
            <span class="prefix"><Icon name="search" :size="14" /></span>
            <input v-model="search" class="input" placeholder="搜索主播、平台或地址" />
          </div>
        </div>
      </div>
      <div class="table-wrap">
        <div class="waiting-wrap">
          <table class="data-table waiting-table">
            <thead>
              <tr>
                <th>主播</th>
                <th>平台</th>
                <th>画质</th>
                <th>状态</th>
                <th>最近更新</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredWaiting" :key="item.room_id">
                <td data-label="主播">
                  <div style="font-weight:600">{{ item.anchor_display || item.anchor_name || '等待识别主播' }}</div>
                  <div class="cell-muted">{{ item.url }}</div>
                </td>
                <td data-label="平台">{{ item.platform_name }}</td>
                <td data-label="画质">{{ item.quality }}</td>
                <td data-label="状态"><span class="badge" :class="stateClass(item.state)">{{ stateLabels[item.state] || item.state }}</span></td>
                <td data-label="最近更新" class="cell-muted">{{ formatTime(item.updated_at) }}</td>
              </tr>
              <tr v-if="!filteredWaiting.length">
                <td colspan="5" class="table-empty">没有处于监测中的直播间</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <ConfirmDialog
      :open="!!confirmDisable"
      title="停用正在录制的直播间"
      :message="`停用“${confirmDisable?.anchor_display || confirmDisable?.anchor_name || '该直播间'}”后，会优雅结束当前录制，并自动把 TS 文件转为 MP4。确定继续？`"
      confirm-text="停用并转 MP4"
      :busy="busy"
      @confirm="disableRecording"
      @cancel="confirmDisable = null"
    />

  </div>
</template>
