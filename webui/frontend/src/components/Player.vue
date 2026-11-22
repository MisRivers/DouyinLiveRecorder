<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../api'
import Icon from './Icon.vue'

const props = defineProps({
  file: { type: Object, default: null },
  playlist: { type: Array, default: () => [] },
  index: { type: Number, default: 0 }
})
const emit = defineEmits(['next', 'prev', 'convert'])

const video = ref(null)
const shell = ref(null)
const error = ref('')
const loading = ref(false)
const playing = ref(false)
const speed = ref(Number(localStorage.getItem('dlr.player.speed') || 1))
const duration = ref(0)
const currentTime = ref(0)
let engine = null
let token = 0
let durationToken = 0

const extension = computed(() => (props.file?.extension || '').toLowerCase())
const isTs = computed(() => extension.value === '.ts')
const supported = computed(() => ['.mp4', '.m4a', '.mp3', '.ts', '.flv'].includes(extension.value))
const hasPrev = computed(() => props.index > 0)
const hasNext = computed(() => props.index < props.playlist.length - 1)
const title = computed(() => props.file?.filename || '未选择文件')

function clock(value) {
  const total = Math.max(0, Number(value || 0))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = Math.floor(total % 60)
  const pad = (part) => String(part).padStart(2, '0')
  return hours ? `${pad(hours)}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`
}

async function loadDuration() {
  const current = ++durationToken
  duration.value = Number(props.file?.duration_seconds || 0)
  currentTime.value = 0
  if (!isTs.value || !props.file?.rel_path || duration.value > 0) return
  try {
    const data = await api(`/files/duration?rel=${encodeURIComponent(props.file.rel_path)}`)
    if (current === durationToken && data?.duration) {
      duration.value = Number(data.duration)
    }
  } catch { /* duration is optional */ }
}

function url() {
  return `/api/files/stream?rel=${encodeURIComponent(props.file?.rel_path || '')}`
}

function destroy() {
  durationToken += 1
  if (engine) {
    try { engine.destroy() } catch { /* ignore */ }
    engine = null
  }
  if (video.value) {
    try {
      video.value.pause()
      video.value.removeAttribute('src')
      video.value.load()
    } catch { /* ignore */ }
  }
  duration.value = 0
  currentTime.value = 0
}

async function setup() {
  error.value = ''
  if (!props.file) return
  const current = ++token
  destroy()
  await nextTick()
  if (!video.value) return
  video.value.playbackRate = speed.value
  if (extension.value === '.mkv') {
    error.value = '浏览器通常不支持 MKV 直接播放，请先转为 MP4。'
    return
  }
  if (!supported.value) {
    error.value = '该格式暂不支持直接播放，请先转为 MP4。'
    return
  }
  loading.value = true
  loadDuration()
  try {
    if (extension.value === '.mp4' || extension.value === '.m4a' || extension.value === '.mp3') {
      video.value.src = url()
      video.value.load()
      await video.value.play().catch(() => {})
    } else if (extension.value === '.flv') {
      const mod = await import('flv.js')
      if (current !== token) return
      const flvjs = mod.default || mod
      if (!flvjs.isSupported()) throw new Error('当前浏览器不支持 FLV 播放')
      engine = flvjs.createPlayer({ type: 'flv', url: url(), isLive: false, hasAudio: true, hasVideo: true })
      engine.attachMediaElement(video.value)
      engine.load()
      engine.play()
    } else if (extension.value === '.ts') {
      if (!window.MediaSource) throw new Error('当前浏览器不支持 MSE，无法直接播放 TS')
      const mod = await import('mpegts.js')
      if (current !== token) return
      const mpegts = mod.default || mod
      if (!mpegts.isSupported()) throw new Error('当前浏览器不支持 mpegts.js 播放')
      engine = mpegts.createPlayer({
        type: 'mse',
        url: url(),
        isLive: false,
        hasAudio: true,
        hasVideo: true,
        lazyLoad: false,
        enableStashBuffer: true
      })
      engine.attachMediaElement(video.value)
      engine.load()
      engine.play()
    }
  } catch (err) {
    error.value = `${err.message}。可以尝试先转为 MP4 再播放。`
  } finally {
    if (current === token) loading.value = false
  }
}

function togglePlay() {
  if (!video.value) return
  if (video.value.paused) video.value.play().catch(() => {})
  else video.value.pause()
}

function changeSpeed() {
  if (video.value) video.value.playbackRate = Number(speed.value)
  localStorage.setItem('dlr.player.speed', String(speed.value))
}

async function fullscreen() {
  try { await shell.value?.requestFullscreen() } catch { /* ignore */ }
}

function onTimeUpdate() {
  if (!props.file || !video.value) return
  currentTime.value = video.value.currentTime || 0
  if (!duration.value) {
    const value = Number(video.value.duration)
    if (Number.isFinite(value) && value > 0) duration.value = value
  }
  const key = `dlr.playback.${props.file.rel_path}`
  localStorage.setItem(key, String(video.value.currentTime || 0))
}

function onLoaded() {
  if (!props.file || !video.value) return
  if (!duration.value) {
    const value = Number(video.value.duration)
    if (Number.isFinite(value) && value > 0) duration.value = value
  }
  const saved = Number(localStorage.getItem(`dlr.playback.${props.file.rel_path}`) || 0)
  const limit = duration.value || video.value.duration || 0
  if (saved > 5 && (!limit || saved < limit - 5)) {
    if (engine && isTs.value) engine.seek(saved)
    else video.value.currentTime = saved
  }
  video.value.playbackRate = speed.value
}

function seekTo(event) {
  if (!video.value) return
  const value = Math.max(0, Number(event.target.value) || 0)
  currentTime.value = value
  if (engine && isTs.value) {
    try { engine.seek(value) } catch { video.value.currentTime = value }
  } else {
    video.value.currentTime = value
  }
}

watch(() => props.file?.rel_path, () => { setup() }, { immediate: true })
watch(() => props.file, (value) => { if (!value) destroy() })
onBeforeUnmount(() => { token += 1; destroy() })
</script>

<template>
  <div ref="shell" class="player-shell">
    <video
      v-show="file && supported && !error"
      ref="video"
      class="player-video"
      :controls="false"
      playsinline
      preload="metadata"
      @click="togglePlay"
      @play="playing = true"
      @pause="playing = false"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoaded"
    />
    <div v-if="!file" class="player-empty">
      <Icon name="video" :size="34" />
      <div>从右侧列表选择一个录制文件开始播放</div>
    </div>
    <div v-else-if="error" class="player-empty">
      <Icon name="alert" :size="30" />
      <div>{{ error }}</div>
      <button class="btn btn-sm" @click="emit('convert', file)">转为 MP4</button>
    </div>
    <div v-if="file && supported && !error" class="player-timeline">
      <span>{{ clock(currentTime) }}</span>
      <input class="timeline-range" type="range" min="0" :max="duration || 0" step="0.1"
             :value="Math.min(currentTime, duration || currentTime)" :disabled="!duration"
             aria-label="播放进度" @input="seekTo" />
      <span>{{ duration ? clock(duration) : '读取时长…' }}</span>
    </div>
    <div class="player-bar">
      <button class="btn btn-icon btn-sm" :disabled="!hasPrev" title="上一集" @click="emit('prev')">
        <Icon name="arrowLeft" :size="16" />
      </button>
      <button class="btn btn-icon btn-sm" :disabled="!file || !!error" title="播放/暂停" @click="togglePlay">
        <Icon :name="playing ? 'pause' : 'play'" :size="16" />
      </button>
      <button class="btn btn-icon btn-sm" :disabled="!hasNext" title="下一集" @click="emit('next')">
        <Icon name="arrowRight" :size="16" />
      </button>
      <div class="player-title" :title="title">{{ loading ? '加载中…' : title }}</div>
      <select v-model.number="speed" class="select" style="width:78px;min-height:30px;padding:4px 8px" @change="changeSpeed">
        <option :value="0.75">0.75x</option>
        <option :value="1">1.0x</option>
        <option :value="1.25">1.25x</option>
        <option :value="1.5">1.5x</option>
        <option :value="2">2.0x</option>
      </select>
      <button class="btn btn-icon btn-sm" title="全屏" @click="fullscreen">
        <Icon name="scan" :size="16" />
      </button>
    </div>
  </div>
</template>
