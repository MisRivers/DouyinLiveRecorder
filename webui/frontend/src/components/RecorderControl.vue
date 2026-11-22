<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { refreshSnapshot, store, toast } from '../store'
import Icon from './Icon.vue'

const route = useRoute()
const open = ref(false)
const busy = ref(false)
const confirmStop = ref(false)
const confirmRestart = ref(false)
const root = ref(null)
const panel = ref(null)

const state = computed(() => store.recorder?.state || 'stopped')
const running = computed(() => ['running', 'starting'].includes(state.value))
const stopping = computed(() => state.value === 'stopping')
const recordingCount = computed(() => Number(store.summary?.recording || 0))
const stateLabel = computed(() => ({
  stopped: '已停止', starting: '启动中', running: '运行中', stopping: '停止中', error: '异常'
}[state.value] || '已停止'))
const dotState = computed(() => {
  if (state.value === 'error') return 'error'
  if (state.value === 'starting' || state.value === 'stopping') return 'pending'
  if (state.value === 'running') return 'running'
  return 'stopped'
})
const panelSub = computed(() => {
  if (state.value === 'error') return '录制程序异常，可尝试重新启动或重启引擎。'
  if (state.value === 'running') return '录制程序运行中，可停止或重启。'
  if (state.value === 'starting') return '录制程序启动中，请稍候。'
  if (state.value === 'stopping') return '正在优雅收尾，请稍候。'
  return '录制程序已停止，启动后按直播间列表检测。'
})

function close() {
  open.value = false
  confirmStop.value = false
  confirmRestart.value = false
}

function resetConfirm() {
  confirmStop.value = false
  confirmRestart.value = false
}

function onDocumentClick(event) {
  if (!open.value) return
  const path = event.composedPath?.() || []
  if (path.includes(root.value) || root.value?.contains(event.target)) return
  close()
}

function onDocumentKeydown(event) {
  if (event.key === 'Escape') close()
}

async function start() {
  busy.value = true
  try {
    await api('/recorder/start', { method: 'POST' })
    toast('录制程序启动中', 'success')
    await refreshSnapshot().catch(() => {})
    close()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
  }
}

async function stop(mode) {
  busy.value = true
  try {
    await api('/recorder/stop', { method: 'POST', body: { mode } })
    toast(mode === 'force' ? '已请求强制停止' : '正在优雅停止录制', 'success')
    await refreshSnapshot().catch(() => {})
    close()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
  }
}

async function restart() {
  busy.value = true
  try {
    await api('/recorder/restart', { method: 'POST' })
    toast('录制程序重启中', 'success')
    await refreshSnapshot().catch(() => {})
    close()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    busy.value = false
  }
}

watch(() => route.fullPath, close)
watch(open, (value) => {
  if (value) nextTick(() => panel.value?.focus())
})

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <div ref="root" class="recorder-control">
    <Transition name="recorder-fade">
      <div v-if="open" class="recorder-backdrop" aria-hidden="true" @click="close" />
    </Transition>
    <button type="button" class="recorder-trigger" :class="dotState"
            :aria-expanded="open" aria-haspopup="dialog"
            :aria-label="`录制控制，当前${stateLabel}`" @click.stop="open = !open">
      <span class="recorder-dot" :class="dotState" />
      <span class="recorder-label">{{ stateLabel }}</span>
      <span v-if="recordingCount" class="recorder-rec"><span class="rec-dot" />REC {{ recordingCount }}</span>
      <Icon class="recorder-chevron" name="down" :size="13" />
    </button>

    <Transition name="dropdown">
      <div v-if="open" ref="panel" class="recorder-panel" role="dialog" aria-label="录制控制" tabindex="-1"
           @click.stop>
        <div class="recorder-panel-head">
          <div>
            <div class="recorder-panel-title">录制控制</div>
            <div class="recorder-panel-sub">{{ panelSub }}</div>
          </div>
          <span class="recorder-state"><span class="recorder-dot" :class="dotState" />{{ stateLabel }}</span>
        </div>

        <div class="recorder-panel-stat">
          <span class="recorder-stat-value" :class="{ active: recordingCount > 0 }">{{ recordingCount }}</span>
          <span class="recorder-stat-label">个直播间正在录制</span>
        </div>

        <div v-if="confirmStop" class="recorder-confirm">
          <div class="recorder-confirm-text">
            优雅停止会等待 FFmpeg 收尾并加入转码队列；只有进程无响应时才使用强制停止。
          </div>
          <div class="recorder-actions">
            <button class="btn btn-primary" :disabled="busy" @click="stop('graceful')">优雅停止</button>
            <button class="btn btn-danger" :disabled="busy" @click="stop('force')">强制停止</button>
          </div>
          <button class="recorder-cancel" :disabled="busy" @click="resetConfirm">取消</button>
        </div>

        <div v-else-if="confirmRestart" class="recorder-confirm">
          <div class="recorder-confirm-text">重启会先优雅停止当前所有录制，再重新加载直播间与配置。</div>
          <div class="recorder-actions">
            <button class="btn btn-danger" :disabled="busy" @click="restart">确认重启</button>
            <button class="btn" :disabled="busy" @click="resetConfirm">取消</button>
          </div>
        </div>

        <div v-else class="recorder-actions">
          <button v-if="!running && !stopping" class="btn btn-primary" :disabled="busy || state === 'starting'" @click="start">
            <Icon name="start" :size="15" /> {{ state === 'error' ? '重新启动' : '启动录制' }}
          </button>
          <button v-if="running" class="btn btn-danger" :disabled="busy" @click="confirmStop = true">
            <Icon name="stop" :size="15" /> 停止录制
          </button>
          <button v-if="state === 'running'" class="btn" :disabled="busy" @click="confirmRestart = true">
            <Icon name="refresh" :size="15" /> 重启引擎
          </button>
          <span v-if="stopping" class="recorder-wait">正在停止，请稍候…</span>
        </div>
        <div v-if="!running && !stopping" class="recorder-hint">启动后会按直播间列表循环检测，开播时自动录制。</div>
      </div>
    </Transition>
  </div>
</template>
