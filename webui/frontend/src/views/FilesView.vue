<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { formatBytes, formatTime, store, toast } from '../store'
import Icon from '../components/Icon.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Modal from '../components/Modal.vue'
import Player from '../components/Player.vue'

const router = useRouter()
const anchors = ref([])
const anchorsTotal = ref(0)
const anchorQuery = ref('')
const anchorSort = ref(readSort('dlr.files.anchors.sort', { sort: 'name', order: 'asc' }))
const selected = ref(null)
const files = ref([])
const fileTotal = ref(0)
const fileSort = ref(readSort('dlr.files.list.sort', { sort: 'name', order: 'asc' }))
const playerOpen = ref(false)
const playerIndex = ref(-1)
const loadingAnchors = ref(false)
const loadingFiles = ref(false)
const systemInfo = ref(null)
const showPath = ref(false)
const batchMode = ref(false)
const selectedPaths = ref([])
const contextMenu = ref({ open: false, x: 0, y: 0, kind: '', anchor: null, file: null })
const confirmDelete = ref(null)
const deleting = ref(false)
let refreshTimer = null

const currentFile = computed(() => (playerIndex.value >= 0 ? files.value[playerIndex.value] : null))
const anchorTitle = computed(() => selected.value?.anchor_name || '全部主播')
const selectedSet = computed(() => new Set(selectedPaths.value))
const selectedCount = computed(() => selectedPaths.value.length)
const allSelected = computed(() => files.value.length > 0 && files.value.every((file) => selectedSet.value.has(file.rel_path)))

function readSort(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || 'null')
    if (value && ['name', 'mtime', 'type'].includes(value.sort) && ['asc', 'desc'].includes(value.order)) return value
  } catch { /* ignore */ }
  return fallback
}

function saveSort(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}

async function loadInfo() {
  try { systemInfo.value = await api('/system/info') } catch { /* ignore */ }
}

async function loadAnchors() {
  loadingAnchors.value = true
  try {
    const data = await api(`/files/anchors?sort=${anchorSort.value.sort}&order=${anchorSort.value.order}&query=${encodeURIComponent(anchorQuery.value)}&page_size=200`)
    anchors.value = data.items
    anchorsTotal.value = data.total
    if (selected.value) {
      const still = anchors.value.find((item) => item.anchor_key === selected.value.anchor_key)
      if (!still) {
        selected.value = null
        files.value = []
        fileTotal.value = 0
        playerOpen.value = false
        playerIndex.value = -1
        selectedPaths.value = []
        batchMode.value = false
      }
    }
    if (!selected.value && anchors.value.length && window.innerWidth > 760) {
      await selectAnchor(anchors.value[0])
    }
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    loadingAnchors.value = false
  }
}

async function loadFiles() {
  if (!selected.value) return
  loadingFiles.value = true
  try {
    const data = await api(`/files?anchor=${encodeURIComponent(selected.value.anchor_key)}&sort=${fileSort.value.sort}&order=${fileSort.value.order}&page_size=500`)
    files.value = data.items
    fileTotal.value = data.total
    const available = new Set(files.value.map((item) => item.rel_path))
    selectedPaths.value = selectedPaths.value.filter((path) => available.has(path))
    if (currentFile.value) {
      const index = files.value.findIndex((item) => item.rel_path === currentFile.value.rel_path)
      if (index < 0) {
        playerOpen.value = false
        playerIndex.value = -1
      } else {
        playerIndex.value = index
      }
    }
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    loadingFiles.value = false
  }
}

async function selectAnchor(anchor) {
  selected.value = anchor
  playerOpen.value = false
  playerIndex.value = -1
  selectedPaths.value = []
  batchMode.value = false
  await loadFiles()
}

async function refreshAnchors() {
  try {
    await api('/system/scan-files', { method: 'POST' })
    toast('已开始扫描录制目录', 'success')
    setTimeout(() => { loadAnchors(); loadInfo() }, 1200)
  } catch (err) {
    toast(err.message, 'error')
  }
}

function applyAnchorSort() {
  saveSort('dlr.files.anchors.sort', anchorSort.value)
  loadAnchors()
}

function applyFileSort() {
  saveSort('dlr.files.list.sort', fileSort.value)
  loadFiles()
}

function play(file) {
  playerIndex.value = files.value.findIndex((item) => item.rel_path === file.rel_path)
  if (playerIndex.value >= 0) playerOpen.value = true
}

function openNewTab() {
  if (!currentFile.value || !selected.value) return
  const href = router.resolve({
    name: 'play',
    query: { anchor: selected.value.anchor_key, rel: currentFile.value.rel_path }
  }).href
  window.open(href, '_blank', 'noopener')
  // 新标签页接管播放，关闭当前弹窗，避免两处同时播放
  playerOpen.value = false
  playerIndex.value = -1
}

async function convert(items) {
  const paths = (Array.isArray(items) ? items : [items]).filter((item) => item?.extension === '.ts').map((item) => item.rel_path)
  if (!paths.length) { toast('没有可转换的 TS 文件', 'warning'); return }
  try {
    const result = await api('/files/convert', { method: 'POST', body: { paths } })
    if (result.queued.length) {
      toast(`已加入转码队列 ${result.queued.length} 个文件`, 'success')
    } else {
      const reasons = [...new Set([...(result.skipped || []), ...(result.rejected || [])]
        .map((item) => item.reason))]
      toast(reasons.length ? `未加入转码：${reasons.join('、')}` : '没有可转换的 TS 文件', 'warning')
    }
  } catch (err) {
    toast(err.message, 'error')
  }
}

function toggleBatchMode() {
  batchMode.value = !batchMode.value
  if (!batchMode.value) selectedPaths.value = []
}

function toggleSelect(file, checked) {
  if (checked) {
    if (!selectedSet.value.has(file.rel_path)) selectedPaths.value.push(file.rel_path)
  } else {
    selectedPaths.value = selectedPaths.value.filter((path) => path !== file.rel_path)
  }
}

function toggleSelectAll() {
  selectedPaths.value = allSelected.value ? [] : files.value.map((file) => file.rel_path)
}

function openContextMenu(event, kind, payload) {
  const width = 196
  const height = 48
  contextMenu.value = {
    open: true,
    x: Math.max(8, Math.min(event.clientX, window.innerWidth - width - 8)),
    y: Math.max(8, Math.min(event.clientY, window.innerHeight - height - 8)),
    kind,
    anchor: kind === 'anchor' ? payload : null,
    file: kind === 'file' ? payload : null
  }
}

function closeContextMenu() {
  if (contextMenu.value.open) contextMenu.value.open = false
}

function contextDelete() {
  const menu = contextMenu.value
  closeContextMenu()
  if (menu.kind === 'anchor' && menu.anchor) {
    askDeleteAnchor(menu.anchor)
  } else if (menu.kind === 'file' && menu.file) {
    askDeleteFiles([menu.file], menu.file.filename)
  }
}

function askDeleteAnchor(anchor) {
  confirmDelete.value = {
    title: '删除该主播全部视频',
    message: `确定删除“${anchor.anchor_name}”的 ${anchor.file_count} 个视频文件吗？正在录制或转码的文件会跳过，删除后不可恢复。`,
    anchorKey: anchor.anchor_key,
    paths: null
  }
}

function askDeleteFiles(items, label) {
  if (!items.length) return
  confirmDelete.value = {
    title: items.length > 1 ? '批量删除录制文件' : '删除录制文件',
    message: items.length > 1
      ? `确定删除已选中的 ${items.length} 个视频文件吗？正在录制或转码的文件会跳过，删除后不可恢复。`
      : `确定删除“${label}”吗？删除后不可恢复。`,
    anchorKey: null,
    paths: items.map((item) => item.rel_path)
  }
}

function askBatchDelete() {
  const items = files.value.filter((file) => selectedSet.value.has(file.rel_path))
  askDeleteFiles(items, '选中的文件')
}

async function applyDelete() {
  const target = confirmDelete.value
  if (!target) return
  deleting.value = true
  try {
    const body = target.anchorKey ? { anchor_key: target.anchorKey } : { paths: target.paths }
    const result = await api('/files/delete', { method: 'POST', body })
    const deleted = result.deleted || []
    const skipped = result.skipped || []
    const rejected = result.rejected || []
    const reasons = [...new Set([...skipped, ...rejected].map((item) => item.reason))]
    if (deleted.length) {
      toast(reasons.length ? `已删除 ${deleted.length} 个，跳过：${reasons.join('、')}` : `已删除 ${deleted.length} 个文件`, 'success')
    } else {
      toast(reasons.length ? `未删除：${reasons.join('、')}` : '没有可删除的文件', 'warning')
    }
    if (currentFile.value && deleted.includes(currentFile.value.rel_path)) {
      playerOpen.value = false
      playerIndex.value = -1
    }
    confirmDelete.value = null
    selectedPaths.value = []
    if (target.anchorKey) batchMode.value = false
    await loadAnchors()
    if (selected.value) await loadFiles()
  } catch (err) {
    toast(err.message, 'error')
  } finally {
    deleting.value = false
  }
}

function onGlobalKey(event) {
  if (event.key === 'Escape') closeContextMenu()
}

function convertAnchor() {
  if (selected.value) convert(files.value)
}

function next() {
  if (playerIndex.value < files.value.length - 1) playerIndex.value += 1
}

function prev() {
  if (playerIndex.value > 0) playerIndex.value -= 1
}

function typeLabel(ext) {
  return (ext || '').replace('.', '').toUpperCase()
}

function conversionBadge(file) {
  if (file.conversion_status === 'pending') return { text: '待转码', cls: 'warning' }
  if (file.conversion_status === 'running') return { text: `转码 ${Math.round((file.conversion_progress || 0) * 100)}%`, cls: 'waiting' }
  if (file.conversion_status === 'failed') return { text: '转码失败', cls: 'error' }
  if (file.conversion_status === 'succeeded') return { text: '已转码', cls: 'recording' }
  if (file.extension === '.ts') return { text: '未转码', cls: 'disabled' }
  return null
}

onMounted(async () => {
  window.addEventListener('keydown', onGlobalKey)
  window.addEventListener('scroll', closeContextMenu, true)
  window.addEventListener('resize', closeContextMenu)
  await Promise.all([loadInfo(), loadAnchors()])
  refreshTimer = window.setInterval(() => { if (!store.wsConnected) { loadAnchors(); loadInfo() } }, 20000)
})

watch(() => store.conversions?.items?.map((item) => item.status).join(','), () => {
  if (selected.value && loadingFiles.value === false) loadFiles()
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  window.removeEventListener('keydown', onGlobalKey)
  window.removeEventListener('scroll', closeContextMenu, true)
  window.removeEventListener('resize', closeContextMenu)
})
</script>

<template>
  <div class="files-page">
    <div class="toolbar page-subbar">
      <button class="btn btn-icon btn-sm" :class="{ 'btn-primary-soft': showPath }"
              :title="showPath ? '隐藏保存目录' : '显示保存目录'" :aria-label="showPath ? '隐藏保存目录' : '显示保存目录'"
              @click="showPath = !showPath">
        <Icon name="info" :size="15" />
      </button>
      <div class="page-subbar-title">文件库</div>
      <span class="card-sub">{{ anchorTitle }} · {{ fileTotal }} 个文件</span>
      <div style="flex:1" />
      <button class="btn btn-sm" title="重新扫描" @click="refreshAnchors">
        <Icon name="scan" :size="14" /><span class="desktop-only">重新扫描目录</span>
      </button>
    </div>
    <div v-if="showPath" class="path-details card">
      <div class="path-detail-row"><span class="info-label">保存目录</span><code>{{ systemInfo?.download_dir || '读取中…' }}</code></div>
      <div class="path-detail-row"><span class="info-label">最近扫描</span><span>{{ formatTime(systemInfo?.last_scan_at) }}</span></div>
    </div>

    <div class="files-layout" :class="{ 'mobile-detail': selected }">
      <aside class="card anchor-panel">
        <div class="card-header" style="padding:14px">
          <div>
            <div class="card-title">主播</div>
            <div class="card-sub">{{ anchorsTotal }} 个分组</div>
          </div>
          <div style="flex:1" />
          <select v-model="anchorSort.sort" class="select compact" @change="applyAnchorSort">
            <option value="name">名称</option>
            <option value="mtime">修改时间</option>
            <option value="type">平台</option>
          </select>
          <button class="btn btn-sm" :title="anchorSort.order === 'asc' ? '当前正序，点击切换为倒序' : '当前倒序，点击切换为正序'"
                  @click="anchorSort.order = anchorSort.order === 'asc' ? 'desc' : 'asc'; applyAnchorSort()">
            {{ anchorSort.order === 'asc' ? '正序' : '倒序' }}
          </button>
        </div>
        <div style="padding:10px 12px;border-bottom:1px solid var(--border)">
          <div class="input-group">
            <span class="prefix"><Icon name="search" :size="14" /></span>
            <input v-model="anchorQuery" class="input" placeholder="搜索主播" @keyup.enter="loadAnchors" />
          </div>
        </div>
        <div class="anchor-list">
          <div v-for="anchor in anchors" :key="anchor.anchor_key" class="anchor-item"
               :class="{ active: selected?.anchor_key === anchor.anchor_key }"
               @click="selectAnchor(anchor)"
               @contextmenu.prevent.stop="openContextMenu($event, 'anchor', anchor)">
            <div class="anchor-name">
              {{ anchor.anchor_name }}
              <span v-if="anchor.has_unconverted_ts" class="badge warning">TS</span>
            </div>
            <div class="anchor-meta">
              <span>{{ anchor.platform_name || '未分类' }}</span>
              <span>{{ anchor.file_count }} 个文件</span>
              <span>{{ formatBytes(anchor.total_bytes) }}</span>
            </div>
          </div>
          <div v-if="!loadingAnchors && !anchors.length" class="empty-state" style="padding:34px 16px">
            <div class="empty-icon"><Icon name="files" :size="22" /></div>
            <div>还没有录制文件</div>
          </div>
        </div>
      </aside>

      <section class="files-main">
        <div class="file-toolbar">
          <button class="btn btn-icon btn-ghost mobile-only" title="返回主播列表" @click="selected = null">
            <Icon name="arrowLeft" :size="18" />
          </button>
          <div>
            <div style="font-weight:600">{{ anchorTitle }}</div>
            <div class="card-sub">{{ fileTotal }} 个文件</div>
          </div>
          <div style="flex:1" />
          <select v-model="fileSort.sort" class="select compact" @change="applyFileSort">
            <option value="name">文件名称</option>
            <option value="mtime">修改时间</option>
            <option value="type">类别</option>
          </select>
          <button class="btn btn-sm" :title="fileSort.order === 'asc' ? '当前正序，点击切换为倒序' : '当前倒序，点击切换为正序'"
                  @click="fileSort.order = fileSort.order === 'asc' ? 'desc' : 'asc'; applyFileSort()">
            {{ fileSort.order === 'asc' ? '正序' : '倒序' }}
          </button>
          <button class="btn btn-sm" :class="{ 'btn-primary-soft': batchMode }"
                  @click="toggleBatchMode">
            <Icon name="check" :size="14" /> {{ batchMode ? '退出批量' : '批量操作' }}
          </button>
          <template v-if="batchMode">
            <button class="btn btn-sm" @click="toggleSelectAll">
              {{ allSelected ? '取消全选' : '全选' }}
            </button>
            <button class="btn btn-sm btn-danger" :disabled="!selectedCount" @click="askBatchDelete">
              <Icon name="trash" :size="14" /> 删除选中 ({{ selectedCount }})
            </button>
          </template>
          <button class="btn btn-sm" :disabled="!selected" @click="convertAnchor">
            <Icon name="download" :size="14" /> 转 MP4
          </button>
        </div>

        <div class="table-wrap">
          <div class="file-list">
            <table class="data-table files-table">
              <thead>
                <tr>
                  <th v-if="batchMode" class="batch-cell">
                    <input type="checkbox" :checked="allSelected" aria-label="全选文件"
                           @change="toggleSelectAll" />
                  </th>
                  <th>文件名</th>
                  <th style="width:80px">类型</th>
                  <th style="width:100px">大小</th>
                  <th style="width:180px">修改时间</th>
                  <th style="width:110px">状态</th>
                  <th style="width:150px;text-align:right">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="file in files" :key="file.rel_path"
                    @contextmenu.prevent.stop="openContextMenu($event, 'file', file)">
                  <td v-if="batchMode" class="batch-cell" data-label="选择">
                    <input type="checkbox" :checked="selectedSet.has(file.rel_path)"
                           :aria-label="`选择 ${file.filename}`"
                           @change="toggleSelect(file, $event.target.checked)" />
                  </td>
                  <td data-label="文件名" class="cell-file">
                    <div class="file-name">{{ file.filename }}</div>
                    <div class="file-sub" v-if="currentFile?.rel_path === file.rel_path && playerOpen">正在播放</div>
                  </td>
                  <td data-label="类型">{{ typeLabel(file.extension) }}</td>
                  <td data-label="大小">{{ formatBytes(file.size_bytes) }}</td>
                  <td data-label="修改时间" class="cell-muted">{{ formatTime(file.mtime) }}</td>
                  <td data-label="状态">
                    <span v-if="conversionBadge(file)" class="badge" :class="conversionBadge(file).cls">
                      {{ conversionBadge(file).text }}
                    </span>
                    <span v-else class="cell-muted">—</span>
                  </td>
                  <td data-label="操作" class="cell-actions">
                    <div class="cell-actions-inner">
                      <button class="btn btn-sm btn-primary-soft" @click="play(file)">
                        <Icon name="play" :size="13" /> 播放
                      </button>
                      <button v-if="file.extension === '.ts'" class="btn btn-sm btn-ghost" @click="convert(file)">转 MP4</button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!loadingFiles && !files.length">
                  <td :colspan="batchMode ? 7 : 6" class="table-empty">该主播暂无录制文件</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>

    <Modal :open="playerOpen && !!currentFile" title="播放"
           wide player @close="playerOpen = false">
      <Player :file="currentFile" :playlist="files" :index="playerIndex"
              @next="next" @prev="prev" @convert="convert" />
      <template #footer>
        <button class="btn" @click="openNewTab"><Icon name="external" :size="14" /> 在新标签打开</button>
        <button v-if="currentFile?.extension === '.ts'" class="btn" @click="convert(currentFile)">转为 MP4</button>
        <button class="btn btn-primary" @click="playerOpen = false">关闭</button>
      </template>
    </Modal>

    <Teleport to="body">
      <div v-if="contextMenu.open" class="context-layer"
           @click="closeContextMenu" @contextmenu.prevent="closeContextMenu">
        <div class="context-menu" :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
             @click.stop>
          <button class="context-menu-item danger" @click="contextDelete">
            <Icon name="trash" :size="15" />
            {{ contextMenu.kind === 'anchor' ? '删除该主播全部视频' : '删除此文件' }}
          </button>
        </div>
      </div>
    </Teleport>

    <ConfirmDialog
      :open="!!confirmDelete"
      :title="confirmDelete?.title || '删除确认'"
      :message="confirmDelete?.message || ''"
      confirm-text="删除"
      danger
      :busy="deleting"
      @confirm="applyDelete"
      @cancel="confirmDelete = null"
    />
  </div>
</template>
