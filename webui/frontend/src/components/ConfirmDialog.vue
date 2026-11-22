<script setup>
import Modal from './Modal.vue'

defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '确认操作' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确认' },
  cancelText: { type: String, default: '取消' },
  danger: { type: Boolean, default: false },
  busy: { type: Boolean, default: false }
})
const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <Modal :open="open" :title="title" @close="emit('cancel')">
    <p style="color: var(--text-secondary); line-height: 1.7">{{ message }}</p>
    <slot />
    <template #footer>
      <button class="btn" :disabled="busy" @click="emit('cancel')">{{ cancelText }}</button>
      <button class="btn" :class="danger ? 'btn-danger' : 'btn-primary'" :disabled="busy" @click="emit('confirm')">
        {{ busy ? '处理中…' : confirmText }}
      </button>
    </template>
  </Modal>
</template>
