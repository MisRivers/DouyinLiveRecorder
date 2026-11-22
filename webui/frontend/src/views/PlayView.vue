<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { toast } from '../store'
import Icon from '../components/Icon.vue'
import Player from '../components/Player.vue'

const route = useRoute()
const router = useRouter()
const files = ref([])
const index = ref(0)
const loading = ref(true)

const current = () => files.value[index.value] || null

async function load() {
  const anchor = String(route.query.anchor || '')
  const rel = String(route.query.rel || '')
  if (!anchor) {
    toast('缺少主播分组参数', 'error')
    loading.value = false
    return
  }
  try {
    const data = await api(`/files?anchor=${encodeURIComponent(anchor)}&sort=name&order=asc&page_size=500`)
    files.value = data.items
    const found = files.value.findIndex((item) => item.rel_path === rel)
    index.value = found >= 0 ? found : 0
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    loading.value = false
  }
}

function next() {
  if (index.value < files.value.length - 1) index.value += 1
}

function prev() {
  if (index.value > 0) index.value -= 1
}

function back() {
  if (window.history.length > 1) router.back()
  else router.push('/files')
}

onMounted(load)
</script>

<template>
  <div class="play-page">
    <header class="play-header">
      <button class="btn btn-icon btn-ghost" style="color:#e2e8f0" aria-label="返回" @click="back">
        <Icon name="arrowLeft" :size="20" />
      </button>
      <div class="play-page-title">{{ current()?.filename || '录制回放' }}</div>
      <div style="flex:1" />
      <a v-if="current()" class="btn btn-sm" style="background:#1e293b;border-color:#334155;color:#e2e8f0"
         :href="`/api/files/stream?rel=${encodeURIComponent(current().rel_path)}`" target="_blank">打开源文件</a>
    </header>
    <main class="play-body">
      <div v-if="loading" class="player-empty" style="border-radius:12px">加载中…</div>
      <Player v-else-if="current()" :file="current()" :playlist="files" :index="index"
              @next="next" @prev="prev" />
      <div v-else class="player-empty">没有可播放的文件</div>
    </main>
  </div>
</template>
