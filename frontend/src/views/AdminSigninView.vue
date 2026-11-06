<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { isPasskeyCancel, openAdmin } from '@/services/passkeys'

// The Django admin's own password form is switched off and redirects here.
// Staff open it with a passkey session; anything else gets an explanation.
const authStore = useAuthStore()
const status = ref<'working' | 'needs-passkey' | 'denied'>('working')

async function tryOpen() {
  status.value = 'working'
  try {
    await openAdmin()
  } catch (error: unknown) {
    const code = (error as { response?: { data?: { code?: string } } })?.response?.data?.code
    status.value = code === 'passkey_required' && authStore.user?.role === 'family' ? 'needs-passkey' : 'denied'
  }
}

async function passkeyThenOpen() {
  try {
    await authStore.loginWithPasskey()
    await tryOpen()
  } catch (error: unknown) {
    if (!isPasskeyCancel(error)) status.value = 'denied'
  }
}

onMounted(tryOpen)
</script>

<template>
  <div class="mx-auto max-w-md px-4 py-12 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-ink">Admin</h1>
    <p v-if="status === 'working'" class="mt-4 text-muted">Opening the admin…</p>
    <div v-else-if="status === 'needs-passkey'" class="mt-4">
      <p class="text-muted">The admin needs you to confirm with your passkey.</p>
      <button
        type="button"
        class="mt-4 w-full rounded-xl bg-primary px-4 py-3 font-semibold text-white hover:bg-primary-dark"
        @click="passkeyThenOpen"
      >
        Use my passkey
      </button>
    </div>
    <p v-else class="mt-4 rounded-xl bg-warn-bg p-4 text-sm text-warn">
      This account can't open the admin.
    </p>
  </div>
</template>
