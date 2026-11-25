<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { toast } from '../store'
import ConfirmDialog from './ConfirmDialog.vue'
import Icon from './Icon.vue'
import InfoTip from './InfoTip.vue'

const platforms = ref([])
const loading = ref(true)
const query = ref('')
const busy = ref(false)
const confirm = ref(null)

const filtered = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return platforms.value
  return platforms.value.filter((item) =>
    item.name.toLowerCase().includes(needle) || item.code.toLowerCase().includes(needle))
})

const enabledCount = computed(() => platforms.value.filter((item) => item.enabled).length)

async function load() {
  loading.value = true
  try {
    platforms.value = await api('/platforms?include_disabled=1')
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    loading.value = false
  }
}

function requestToggle(item, value) {
  if (!value && item.room_count > 0) {
    confirm.value = { item, value }
    return
  }
  applyToggle(item, value)
}

async function applyToggle(item, value) {
  busy.value = true
  try {
    const result = await api(`/platforms/${item.code}`, { method: 'PATCH', body: { enabled: value } })
    item.enabled = result.enabled
    toast(value ? `${item.name} 已启用` : `${item.name} 已禁用`, 'success')
  } catch (err) {
    toast(err.message, 'error')
    await load()
  } finally {
    busy.value = false
    confirm.value = null
  }
}

function confirmToggle() {
  if (!confirm.value) return
  applyToggle(confirm.value.item, confirm.value.value)
}

onMounted(load)
</script>

<template>
  <div class="auto-panel">
    <div class="auto-head">
      <div class="auto-head-title">
        <div class="card-title">
          平台管理
          <InfoTip text="禁用后不再出现在新增/编辑直播间的平台列表，已有直播间暂停检测与录制。禁用不会删除直播间、录制文件或历史会话，重新启用后按房间状态与录制计划自动恢复。" />
        </div>
      </div>
      <span class="platform-count">{{ enabledCount }} / {{ platforms.length }} 个启用</span>
    </div>

    <div class="platform-toolbar">
      <div class="input-group" style="max-width:260px;width:100%">
        <span class="prefix"><Icon name="search" :size="14" /></span>
        <input v-model="query" class="input" placeholder="搜索平台名称或标识" />
      </div>
      <span class="cell-muted">共 {{ filtered.length }} 个平台</span>
    </div>

    <div v-if="loading" class="platform-list">
      <div v-for="n in 4" :key="n" class="platform-row">
        <div class="skeleton" style="height:18px;width:140px" />
      </div>
    </div>

    <TransitionGroup v-else name="platform-row" tag="div" class="platform-list">
      <div v-for="item in filtered" :key="item.code" class="platform-row"
           :class="{ disabled: !item.enabled }">
        <div class="platform-identity">
          <span class="platform-dot" :class="{ off: !item.enabled }" />
          <div>
            <div class="platform-name">{{ item.name }}</div>
            <div class="platform-code mono">{{ item.code }}</div>
          </div>
        </div>
        <div class="platform-tags">
          <span v-if="item.needs_cookie" class="tag">需要 Cookie</span>
          <span v-if="item.proxy_recommended" class="tag">建议代理</span>
        </div>
        <div class="platform-rooms">
          <span class="platform-rooms-value">{{ item.room_count }}</span>
          <span class="cell-muted">个直播间</span>
        </div>
        <div class="platform-state">
          <span class="badge" :class="item.enabled ? 'success' : 'disabled'">
            {{ item.enabled ? '已启用' : '已禁用' }}
          </span>
          <label class="switch" :title="item.enabled ? '禁用平台' : '启用平台'">
            <input type="checkbox" :checked="item.enabled" :disabled="busy"
                   :aria-label="`${item.enabled ? '禁用' : '启用'}${item.name}`"
                   @change="requestToggle(item, $event.target.checked)" />
            <span class="switch-track"><span class="switch-thumb" /></span>
          </label>
        </div>
      </div>
    </TransitionGroup>

    <div v-if="!loading && !filtered.length" class="empty-state">没有匹配的平台</div>

    <ConfirmDialog
      :open="!!confirm"
      title="禁用直播平台"
      :message="confirm ? `禁用“${confirm.item.name}”后，其下 ${confirm.item.room_count} 个已启用直播间会暂停检测与录制，正在录制的房间将优雅结束。确定继续？` : ''"
      confirm-text="禁用平台"
      danger
      :busy="busy"
      @confirm="confirmToggle"
      @cancel="confirm = null"
    />
  </div>
</template>
