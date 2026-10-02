<script setup lang="ts">
/**
 * Photos are never public — every fetch needs the visitor's bearer token, so a
 * plain `<img src>` can't load one directly (the browser won't attach the
 * Authorization header). This fetches the bytes through the authenticated
 * `api` client and displays them as an object URL instead.
 */
import { onBeforeUnmount, ref, watch } from 'vue'
import api from '@/services/api'

const props = defineProps<{ src: string; alt?: string }>()

const objectUrl = ref<string | null>(null)
const failed = ref(false)

async function load() {
  failed.value = false
  const previous = objectUrl.value
  objectUrl.value = null
  try {
    const response = await api.get<Blob>(props.src, { responseType: 'blob' })
    objectUrl.value = URL.createObjectURL(response.data)
  } catch {
    failed.value = true
  } finally {
    if (previous) URL.revokeObjectURL(previous)
  }
}

watch(() => props.src, load, { immediate: true })
onBeforeUnmount(() => {
  if (objectUrl.value) URL.revokeObjectURL(objectUrl.value)
})
</script>

<template>
  <img v-if="objectUrl" :src="objectUrl" :alt="alt ?? ''" />
  <div v-else-if="failed" class="flex items-center justify-center bg-line text-xs text-muted">
    Couldn't load
  </div>
  <div v-else class="animate-pulse bg-line" />
</template>
