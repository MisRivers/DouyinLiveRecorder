<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { clearAuth, connectWs, refreshSnapshot, store } from '../store'
import Icon from './Icon.vue'
import RecorderControl from './RecorderControl.vue'

const route = useRoute()
const router = useRouter()
const fallbackTimer = ref(null)
const showTop = ref(false)
const userMenuOpen = ref(false)
const userPanel = ref(null)

const navItems = [
  { to: '/live', label: '录制状态', icon: 'live' },
  { to: '/files', label: '录制文件', icon: 'files' },
  { to: '/rooms', label: '直播间管理', icon: 'rooms' },
  { to: '/settings', label: '系统配置', icon: 'settings' }
]

async function logout() {
  userMenuOpen.value = false
  try { await api('/auth/logout', { method: 'POST' }) } catch { /* ignore */ }
  clearAuth()
  router.push('/login')
}

function closeUserMenu() {
  userMenuOpen.value = false
}

function onDocumentClick(event) {
  if (!userMenuOpen.value) return
  if (!userPanel.value?.contains(event.target)) userMenuOpen.value = false
}

function onDocumentKeydown(event) {
  if (event.key === 'Escape') userMenuOpen.value = false
}

function onUnauthorized() {
  clearAuth()
  if (route.path !== '/login') router.push({ name: 'login', query: { next: route.fullPath } })
}

function onScroll() {
  showTop.value = window.scrollY > 320
}

function scrollTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(() => {
  window.addEventListener('dlr:unauthorized', onUnauthorized)
  window.addEventListener('scroll', onScroll, { passive: true })
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onDocumentKeydown)
  if (store.user) {
    connectWs()
    refreshSnapshot().catch(() => {})
    fallbackTimer.value = window.setInterval(() => {
      if (!store.wsConnected) refreshSnapshot().catch(() => {})
    }, 8000)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('dlr:unauthorized', onUnauthorized)
  window.removeEventListener('scroll', onScroll)
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onDocumentKeydown)
  if (fallbackTimer.value) window.clearInterval(fallbackTimer.value)
})
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <img class="brand-mark brand-logo" src="/assets/logo.svg" alt="LiveRecorder" width="34" height="34" />
        <div class="brand-text">
          <div class="brand-name">LiveRecorder</div>
          <div class="brand-sub">Web 管理端</div>
        </div>
      </div>
      <nav class="nav">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-item">
          <Icon :name="item.icon" :size="18" />
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-footer">
        <div ref="userPanel" class="user-panel">
          <button type="button" class="user-trigger" :aria-expanded="userMenuOpen"
                  aria-haspopup="menu" aria-label="账号菜单" @click.stop="userMenuOpen = !userMenuOpen">
            <span class="avatar-wrap">
              <span class="avatar">{{ (store.user?.username || 'A').slice(0, 1).toUpperCase() }}</span>
              <span class="avatar-presence" :class="{ offline: !store.wsConnected }" />
            </span>
            <span class="user-text">
              <span class="user-name">{{ store.user?.username }}</span>
              <span class="user-role">管理员 · {{ store.wsConnected ? '实时' : '轮询' }}</span>
            </span>
            <Icon class="user-chevron" name="down" :size="14" />
          </button>
          <Transition name="dropdown">
            <div v-if="userMenuOpen" class="user-menu" role="menu" aria-label="账号操作">
              <div class="user-menu-head">
                <div class="user-menu-name">{{ store.user?.username || '管理员' }}</div>
                <div class="user-menu-sub">当前登录账号</div>
              </div>
              <RouterLink to="/system" class="user-menu-item" role="menuitem" @click="closeUserMenu">
                <Icon name="info" :size="15" /> 系统信息
              </RouterLink>
              <a class="user-menu-item" href="https://github.com/MisRivers/DouyinLiveRecorder"
                 target="_blank" rel="noopener" role="menuitem" @click="closeUserMenu">
                <Icon name="github" :size="15" /> GitHub 项目
              </a>
              <div class="user-menu-divider" />
              <button type="button" class="user-menu-item danger" role="menuitem" @click="logout">
                <Icon name="logout" :size="15" /> 退出登录
              </button>
            </div>
          </Transition>
        </div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="page-title">{{ route.meta.title || '管理端' }}</div>
        <div class="topbar-spacer" />
        <div class="topbar-actions">
          <span class="ws-state desktop-only"><span class="ws-dot" :class="{ on: store.wsConnected }" />{{ store.wsConnected ? '实时' : '轮询' }}</span>
          <RecorderControl />
          <RouterLink v-if="route.name !== 'system'" to="/system" class="btn btn-sm mobile-only" title="系统信息与账号">系统信息</RouterLink>
        </div>
      </header>
      <main class="content">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>
    </div>

    <button v-if="showTop" class="back-to-top" aria-label="回到顶部" @click="scrollTop">
      <Icon name="up" :size="18" />
    </button>

    <nav class="mobile-nav">
      <div class="nav">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-item">
          <Icon :name="item.icon" :size="20" />
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </div>
    </nav>
  </div>
</template>
