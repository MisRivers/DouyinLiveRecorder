<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { clearAuth, formatBytes, formatTime, store, toast } from '../store'
import Icon from '../components/Icon.vue'

const router = useRouter()

const info = ref(null)
const health = ref(null)
const logs = ref([])
const logFile = ref('')
const loading = ref(true)
const busy = ref(false)
const password = reactive({ current: '', next: '', confirm: '' })
const passwordError = ref('')
const updateInfo = ref(null)
const updateLoading = ref(false)
const updateError = ref('')

async function load() {
  loading.value = true
  try {
    const [systemInfo, healthData, logData] = await Promise.all([
      api('/system/info'),
      fetch('/api/system/health').then((res) => res.json()).then((payload) => payload.data),
      api('/system/logs?limit=200')
    ])
    info.value = systemInfo
    health.value = healthData
    logs.value = logData.lines
    logFile.value = logData.file
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    loading.value = false
  }
}

async function refreshLogs() {
  try {
    const data = await api('/system/logs?limit=300')
    logs.value = data.lines
    logFile.value = data.file
  } catch (err) {
    toast(err.message, 'error')
  }
}

async function loadUpdate(force = false) {
  updateLoading.value = true
  updateError.value = ''
  try {
    updateInfo.value = await api(`/system/update${force ? '?force=1' : ''}`)
  } catch (err) {
    updateError.value = err.message
  } finally {
    updateLoading.value = false
  }
}

async function changePassword() {
  passwordError.value = ''
  if (!password.current) { passwordError.value = '请输入当前密码'; return }
  if (password.next !== password.confirm) { passwordError.value = '两次输入的新密码不一致'; return }
  busy.value = true
  try {
    await api('/auth/password', {
      method: 'POST',
      body: { current_password: password.current, new_password: password.next }
    })
    password.current = ''
    password.next = ''
    password.confirm = ''
    toast('密码已更新', 'success')
  } catch (err) {
    passwordError.value = err.message
  } finally {
    busy.value = false
  }
}

async function logout() {
  try { await api('/auth/logout', { method: 'POST' }) } catch { /* ignore */ }
  clearAuth()
  router.push('/login')
}

onMounted(() => {
  load()
  loadUpdate()
})
</script>

<template>
  <div>
    <div class="toolbar system-toolbar" style="margin-bottom:14px">
      <div class="system-heading">
        <div style="font-weight:600">运行概况</div>
        <div class="card-sub">运行目录、版本、环境检查与日志。</div>
      </div>
      <div style="flex:1" />
      <button class="btn btn-sm" title="刷新" @click="load"><Icon name="refresh" :size="14" /><span class="desktop-only">刷新</span></button>
      <a class="btn btn-icon btn-sm mobile-only" href="https://github.com/MisRivers/DouyinLiveRecorder"
         target="_blank" rel="noopener" title="GitHub 项目" aria-label="GitHub 项目">
        <Icon name="github" :size="15" />
      </a>
      <button class="btn btn-sm mobile-only" title="退出登录" @click="logout"><Icon name="logout" :size="14" /></button>
    </div>

    <div v-if="loading" class="card" style="padding:20px">
      <div class="skeleton" style="height:80px" />
    </div>

    <template v-else>
      <div class="info-grid" style="margin-bottom:16px">
        <div class="info-item">
          <div class="info-label">当前账号</div>
          <div class="info-value">{{ store.user?.username || '—' }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">应用版本</div>
          <div class="info-value">v{{ info?.app_version || info?.version || '—' }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">上游版本</div>
          <div class="info-value">{{ info?.upstream_version || '未知' }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">数据库大小</div>
          <div class="info-value">{{ formatBytes(info?.db_size) }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">录制保存目录</div>
          <div class="info-value">{{ info?.download_dir }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">配置目录</div>
          <div class="info-value">{{ info?.config_dir }}</div>
        </div>
        <div class="info-item">
          <div class="info-label">最近文件扫描</div>
          <div class="info-value">{{ formatTime(info?.last_scan_at) }}</div>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-header">
          <div>
            <div class="card-title">版本更新</div>
            <div class="card-sub">读取 GitHub Releases 的最新版本，不会自动替换程序文件。</div>
          </div>
          <div style="flex:1" />
          <button class="btn btn-sm" :disabled="updateLoading" @click="loadUpdate(true)">
            {{ updateLoading ? '检查中…' : '检查更新' }}
          </button>
        </div>
        <div class="card-body">
          <div class="info-grid">
            <div class="info-item">
              <div class="info-label">当前版本</div>
              <div class="info-value">v{{ info?.app_version || updateInfo?.current || '—' }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">最新版本</div>
              <div class="info-value">{{ updateInfo?.latest ? `v${updateInfo.latest}` : '暂无发行版' }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">状态</div>
              <div class="info-value" style="font-weight:500">
                <span v-if="updateLoading">检查中…</span>
                <span v-else-if="updateError" style="color:var(--danger)">{{ updateError }}</span>
                <span v-else-if="updateInfo?.update_available" style="color:var(--warning)">发现新版本</span>
                <span v-else-if="updateInfo?.latest">已是最新</span>
                <span v-else>暂无发行版</span>
              </div>
            </div>
            <div class="info-item">
              <div class="info-label">发行版页面</div>
              <div class="info-value">
                <a :href="updateInfo?.release_url || 'https://github.com/MisRivers/DouyinLiveRecorder/releases'"
                   target="_blank" rel="noopener">打开 GitHub Releases</a>
              </div>
            </div>
          </div>
          <div v-if="updateInfo?.notes" class="card-sub"
               style="margin-top:10px;white-space:pre-wrap;max-height:120px;overflow:auto">{{ updateInfo.notes }}</div>
          <div class="card-sub" style="margin-top:8px">
            当前版本支持检测更新并跳转发行版下载；自动替换 EXE 将在后续版本提供。
          </div>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-header">
          <div>
            <div class="card-title">环境检查</div>
            <div class="card-sub">启动失败时先看这里。</div>
          </div>
          <div style="flex:1" />
          <span class="badge" :class="health?.status === 'ok' ? 'success' : 'warning'">{{ health?.status }}</span>
        </div>
        <div class="card-body">
          <div class="info-grid">
            <div v-for="(value, key) in health?.checks || {}" :key="key" class="info-item">
              <div class="info-label">{{ key }}</div>
              <div class="info-value" style="font-weight:500">{{ value || '—' }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-header">
          <div>
            <div class="card-title">修改密码</div>
            <div class="card-sub">修改后其他已登录会话会被退出。</div>
          </div>
        </div>
        <div class="card-body">
          <div class="form-grid" style="max-width:640px">
            <div class="field span-2">
              <label class="field-label">当前密码</label>
              <input v-model="password.current" class="input" type="password" autocomplete="current-password" />
            </div>
            <div class="field">
              <label class="field-label">新密码</label>
              <input v-model="password.next" class="input" type="password" autocomplete="new-password" />
            </div>
            <div class="field">
              <label class="field-label">确认新密码</label>
              <input v-model="password.confirm" class="input" type="password" autocomplete="new-password" />
            </div>
            <div v-if="passwordError" class="form-error span-2">{{ passwordError }}</div>
            <div class="span-2">
              <button class="btn btn-primary" :disabled="busy" @click="changePassword">
                {{ busy ? '保存中…' : '更新密码' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">运行日志</div>
            <div class="card-sub">{{ logFile || '暂无日志文件' }} · 最近 200 行</div>
          </div>
          <div style="flex:1" />
          <button class="btn btn-sm" @click="refreshLogs">刷新日志</button>
        </div>
        <div class="card-body">
          <div class="log-box">{{ logs.length ? logs.join('\n') : '暂无日志' }}</div>
        </div>
      </div>
    </template>
  </div>
</template>
