<script setup>
import { ref } from 'vue'
import Icon from './Icon.vue'

defineProps({
  text: { type: String, default: '' }
})

const hover = ref(false)
const pinned = ref(false)
const visible = () => hover.value || pinned.value

function toggle() {
  pinned.value = !pinned.value
}

function close() {
  pinned.value = false
}
</script>

<template>
  <span class="info-tip" role="button" tabindex="0" :aria-label="text"
        :aria-expanded="visible()"
        @mouseenter="hover = true"
        @mouseleave="hover = false"
        @focus="hover = true"
        @blur="hover = false; close()"
        @click.stop="toggle"
        @keydown.enter.prevent="toggle"
        @keydown.space.prevent="toggle">
    <Icon name="info" :size="14" />
    <Transition name="dropdown">
      <span v-if="visible()" class="info-tip-pop" role="tooltip">{{ text }}</span>
    </Transition>
  </span>
</template>
