import { createRouter, createWebHistory } from 'vue-router'
import { initAuth, store } from './store'
import AppShell from './components/AppShell.vue'
import LoginView from './views/LoginView.vue'
import LiveView from './views/LiveView.vue'
import FilesView from './views/FilesView.vue'
import RoomsView from './views/RoomsView.vue'
import SettingsView from './views/SettingsView.vue'
import SystemView from './views/SystemView.vue'
import PlayView from './views/PlayView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true, title: '登录' } },
    { path: '/play', name: 'play', component: PlayView, meta: { title: '录制回放' } },
    {
      path: '/',
      component: AppShell,
      children: [
        { path: '', redirect: '/live' },
        { path: 'live', name: 'live', component: LiveView, meta: { title: '录制状态' } },
        { path: 'files', name: 'files', component: FilesView, meta: { title: '录制文件' } },
        { path: 'rooms', name: 'rooms', component: RoomsView, meta: { title: '直播间管理' } },
        { path: 'settings', name: 'settings', component: SettingsView, meta: { title: '系统配置' } },
        { path: 'system', name: 'system', component: SystemView, meta: { title: '系统信息' } }
      ]
    }
  ]
})

router.beforeEach(async (to) => {
  if (!store.ready) await initAuth()
  if (to.meta.public) {
    if (store.user && to.name === 'login') return { name: 'live' }
    return true
  }
  if (!store.user) return { name: 'login', query: { next: to.fullPath } }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · DouyinLiveRecorder` : 'DouyinLiveRecorder'
})

export default router
