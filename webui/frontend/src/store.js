import { reactive } from 'vue'
import { api } from './api'

export const store = reactive({
  ready: false,
  setupRequired: false,
  user: null,
  csrf: '',
  recorder: { state: 'stopped' },
  summary: { recording: 0, waiting: 0, error: 0, enabled: 0, total: 0 },
  recordings: [],
  waiting: { items: [], total: 0, page: 1, page_size: 200 },
  conversions: { items: [], total: 0 },
  wsConnected: false,
  toasts: []
})

let socket = null
let reconnectTimer = null
let toastId = 0

export async function initAuth() {
  try {
    const data = await api('/auth/status')
    store.setupRequired = !!data.setup_required
    store.user = data.user
    store.csrf = data.csrf_token || ''
  } catch {
    store.user = null
  } finally {
    store.ready = true
  }
}

export function setAuth(user, csrf) {
  store.user = user
  store.csrf = csrf || ''
  store.setupRequired = false
  connectWs()
}

export function clearAuth() {
  store.user = null
  store.csrf = ''
  disconnectWs()
}

export function applySnapshot(data) {
  if (!data) return
  if (data.recorder) store.recorder = data.recorder
  if (data.summary) store.summary = data.summary
  if (data.recordings) store.recordings = data.recordings
  if (data.waiting) store.waiting = data.waiting
  if (data.conversions) store.conversions = data.conversions
}

export async function refreshSnapshot() {
  const [summary, recordings, waiting, conversions] = await Promise.all([
    api('/live/summary'),
    api('/live/recordings'),
    api('/live/waiting?page_size=200'),
    api('/files/conversions?page_size=20')
  ])
  applySnapshot({
    recorder: summary.recorder,
    summary,
    recordings: recordings.items,
    waiting,
    conversions
  })
}

export function connectWs() {
  if (!store.user || socket) return
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  socket = new WebSocket(`${protocol}//${location.host}/api/ws/events`)
  socket.onopen = () => { store.wsConnected = true }
  socket.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'snapshot' || message.type === 'tick') applySnapshot(message.data)
    } catch { /* ignore malformed frames */ }
  }
  socket.onclose = () => {
    store.wsConnected = false
    socket = null
    if (store.user) {
      clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connectWs, 2500)
    }
  }
  socket.onerror = () => { try { socket.close() } catch { /* ignore */ } }
}

export function disconnectWs() {
  clearTimeout(reconnectTimer)
  reconnectTimer = null
  if (socket) {
    socket.onclose = null
    try { socket.close() } catch { /* ignore */ }
    socket = null
  }
  store.wsConnected = false
}

export function toast(message, type = 'info', timeout = 3200) {
  const id = ++toastId
  store.toasts.push({ id, message, type })
  setTimeout(() => dismissToast(id), timeout)
}

export function dismissToast(id) {
  const index = store.toasts.findIndex((item) => item.id === id)
  if (index >= 0) store.toasts.splice(index, 1)
}

export function formatBytes(bytes) {
  const value = Number(bytes || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(2)} GB`
}

export function formatDuration(seconds) {
  const total = Math.max(0, Number(seconds || 0))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = Math.floor(total % 60)
  return [hours, minutes, secs].map((value) => String(value).padStart(2, '0')).join(':')
}

export function formatTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return value
  }
}
