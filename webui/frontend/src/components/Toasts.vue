<script setup>
import { store, dismissToast } from '../store'
</script>

<template>
  <div class="toast-wrap" role="status" aria-live="polite" aria-atomic="false">
    <TransitionGroup name="fade">
      <div v-for="item in store.toasts" :key="item.id" class="toast" :class="item.type" @click="dismissToast(item.id)">
        {{ item.message }}
      </div>
    </TransitionGroup>
  </div>
</template>
