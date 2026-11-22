<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { initAuth, refreshSnapshot, setAuth, store, toast } from '../store'
import Icon from '../components/Icon.vue'

const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const busy = ref(false)
const setupMode = computed(() => store.setupRequired)

onMounted(async () => {
  if (!store.ready) await initAuth()
  if (store.user) router.replace(String(route.query.next || '/live'))
})

async function submit() {
  error.value = ''
  if (!username.value.trim()) { error.value = '请输入用户名'; return }
  if (!password.value) { error.value = '请输入密码'; return }
  if (setupMode.value && password.value !== confirm.value) { error.value = '两次输入的密码不一致'; return }
  busy.value = true
  try {
    const path = setupMode.value ? '/auth/setup' : '/auth/login'
    const body = setupMode.value
      ? { username: username.value.trim(), password: password.value, password_confirm: confirm.value }
      : { username: username.value.trim(), password: password.value }
    const data = await api(path, { method: 'POST', body })
    setAuth(data.user, data.csrf_token)
    await refreshSnapshot().catch(() => {})
    toast(setupMode.value ? '管理员已创建' : '登录成功', 'success')
    router.replace(String(route.query.next || '/live'))
  } catch (err) {
    if (err.details?.retry_after_seconds) {
      error.value = `${err.message}，请在 ${err.details.retry_after_seconds} 秒后重试`
    } else {
      error.value = err.message
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-brand">
      <div class="brand">
        <img class="brand-mark brand-logo" src="/assets/logo.svg" alt="LiveRecorder" width="34" height="34" />
        <div>
          <div class="brand-name">LiveRecorder</div>
          <div class="brand-sub">Web 管理端</div>
        </div>
      </div>
      <div>
        <h1 class="login-heading">把直播录制，放到浏览器里管理。</h1>
        <p class="login-copy">
          启动与停止录制、管理直播间、调整全部配置、查看录制文件，都在同一个页面完成。
        </p>
        <div class="login-points">
          <div class="login-point"><Icon name="live" :size="16" /> 实时查看录制与等待状态</div>
          <div class="login-point"><Icon name="files" :size="16" /> 按主播浏览与播放录制文件</div>
          <div class="login-point"><Icon name="settings" :size="16" /> 配置项集中管理，自动生成 ini</div>
        </div>
      </div>
      <div class="login-foot" style="text-align:left">DouyinLiveRecorder · 本地部署</div>
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div class="login-mobile-brand">
          <img class="brand-mark brand-logo" src="/assets/logo.svg" alt="LiveRecorder" width="34" height="34" />
          <div>
            <div class="brand-name">LiveRecorder</div>
            <div class="brand-sub">Web 管理端</div>
          </div>
        </div>
        <h2 class="login-title">{{ setupMode ? '创建管理员' : '登录管理端' }}</h2>
        <p class="login-sub">{{ setupMode ? '首次使用，请设置管理员账号与密码。' : '请输入管理员账号继续。' }}</p>
        <form class="login-form" @submit.prevent="submit">
          <div class="field">
            <label class="field-label" for="username">用户名</label>
            <input id="username" v-model="username" class="input" autocomplete="username" placeholder="请输入用户名" />
          </div>
          <div class="field">
            <label class="field-label" for="password">密码</label>
            <input id="password" v-model="password" class="input" type="password"
                   :autocomplete="setupMode ? 'new-password' : 'current-password'" placeholder="请输入密码" />
          </div>
          <div v-if="setupMode" class="field">
            <label class="field-label" for="confirm">确认密码</label>
            <input id="confirm" v-model="confirm" class="input" type="password" autocomplete="new-password"
                   placeholder="请再次输入密码" />
            <span class="field-hint">至少 10 位，包含字母与数字。</span>
          </div>
          <div v-if="error" class="login-error">{{ error }}</div>
          <button class="btn btn-primary btn-block" type="submit" :disabled="busy">
            {{ busy ? '请稍候…' : (setupMode ? '创建并进入' : '登录') }}
          </button>
        </form>
        <a class="login-github" href="https://github.com/MisRivers/DouyinLiveRecorder"
           target="_blank" rel="noopener">
          <Icon name="github" :size="15" /> GitHub 项目
        </a>
      </div>
    </section>
  </div>
</template>
