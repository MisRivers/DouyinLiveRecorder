<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  wide: { type: Boolean, default: false },
  player: { type: Boolean, default: false }
})
const emit = defineEmits(['close'])

const modalEl = ref(null)
const titleId = `modal-title-${Math.random().toString(36).slice(2)}`
let previousOverflow = ''
let previousActive = null

function focusableElements() {
  if (!modalEl.value) return []
  return [...modalEl.value.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  )].filter((el) => el.getClientRects().length > 0)
}

function restoreFocus() {
  const target = previousActive
  previousActive = null
  nextTick(() => {
    if (target && document.contains(target)) target.focus?.()
  })
}

function lockScroll(locked) {
  if (typeof document === 'undefined') return
  if (locked) {
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = previousOverflow || ''
  }
}

function onKey(event) {
  if (event.key === 'Escape') {
    emit('close')
    return
  }
  if (event.key !== 'Tab') return
  const items = focusableElements()
  if (!items.length) {
    event.preventDefault()
    modalEl.value?.focus()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  if (!modalEl.value?.contains(document.activeElement)) {
    event.preventDefault()
    first.focus()
    return
  }
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.open, (value) => {
  lockScroll(value)
  if (value) {
    previousActive = document.activeElement
    window.addEventListener('keydown', onKey)
    nextTick(() => modalEl.value?.focus())
  } else {
    window.removeEventListener('keydown', onKey)
    restoreFocus()
  }
}, { immediate: true })

onBeforeUnmount(() => {
  lockScroll(false)
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" :class="{ 'player-backdrop': player }" @click.self="emit('close')">
        <div ref="modalEl" class="modal" :class="{ wide, 'player-modal': player }"
             role="dialog" aria-modal="true" :aria-labelledby="title ? titleId : undefined" tabindex="-1">
          <div class="modal-header">
            <div :id="titleId" class="modal-title">{{ title }}</div>
            <div style="flex:1" />
            <button class="btn btn-icon btn-ghost" aria-label="关闭" @click="emit('close')">
              <Icon name="x" :size="18" />
            </button>
          </div>
          <div class="modal-body"><slot /></div>
          <div v-if="$slots.footer" class="modal-footer"><slot name="footer" /></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
