<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import type { Passkey } from '@/types/auth'
import {
  changePassword,
  deletePasskey,
  isPasskeyCancel,
  listPasskeys,
  openAdmin,
  passkeysSupported
} from '@/services/passkeys'

const authStore = useAuthStore()
const user = computed(() => authStore.user)
const canUsePasskey = passkeysSupported()

const passkeys = ref<Passkey[]>([])
const newPasskeyName = ref('')
const busy = ref(false)
const message = ref('')
const errorMessage = ref('')

const claimEmail = ref('')
const claimPassword = ref('')
const newPassword = ref('')

function errorText(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: Record<string, unknown> } })?.response?.data
  for (const field of ['email', 'password', 'new_password']) {
    const value = data?.[field]
    if (Array.isArray(value) && value.length) return String(value[0])
  }
  return typeof data?.detail === 'string' ? data.detail : fallback
}

async function run(action: () => Promise<void>, success: string, fallback: string) {
  busy.value = true
  message.value = ''
  errorMessage.value = ''
  try {
    await action()
    message.value = success
  } catch (error: unknown) {
    if (!isPasskeyCancel(error)) errorMessage.value = errorText(error, fallback)
  } finally {
    busy.value = false
  }
}

async function refreshPasskeys() {
  passkeys.value = await listPasskeys()
  if (user.value) authStore.storeUser({ ...user.value, passkey_count: passkeys.value.length })
}

function addPasskey() {
  return run(
    async () => {
      await authStore.addPasskey(newPasskeyName.value)
      newPasskeyName.value = ''
      await refreshPasskeys()
    },
    'Passkey saved. Next time, sign in with it instead of your password.',
    "The passkey couldn't be saved. Please try again."
  )
}

function removePasskey(passkey: Passkey) {
  return run(
    async () => {
      await deletePasskey(passkey.id)
      await refreshPasskeys()
    },
    `Removed “${passkey.name}”.`,
    "That passkey couldn't be removed."
  )
}

function claimAccount() {
  return run(
    async () => {
      await authStore.claimAccount(claimEmail.value, claimPassword.value)
      claimPassword.value = ''
    },
    'Saved. You can now sign in with your email and password on any device.',
    "That didn't save. Please try again."
  )
}

function submitNewPassword() {
  return run(
    async () => {
      await changePassword(newPassword.value)
      newPassword.value = ''
    },
    'Password changed.',
    "The password wasn't changed. Please try again."
  )
}

function goToAdmin() {
  return run(openAdmin, '', "The admin couldn't be opened.")
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString() : 'never'
}

onMounted(() => {
  refreshPasskeys().catch(() => {
    errorMessage.value = "Your passkeys couldn't be loaded."
  })
})
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-ink">Account</h1>
    <p class="mt-1 text-muted">{{ user?.name }} · {{ user?.has_password === false ? 'no email yet' : user?.email }}</p>

    <div v-if="message" class="mt-5 rounded-xl bg-ok-bg px-4 py-3 text-sm text-ok" role="status">
      {{ message }}
    </div>
    <div v-if="errorMessage" class="mt-5 rounded-xl bg-warn-bg px-4 py-3 text-sm text-warn" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Visitors who joined before passwords existed: one-time upgrade -->
    <section
      v-if="user?.has_password === false"
      class="mt-6 rounded-2xl border border-line bg-surface p-6 shadow-sm"
    >
      <h2 class="text-lg font-semibold text-ink">Add an email and password</h2>
      <p class="mt-1 text-sm text-muted">
        Do this once so you can sign in on your other devices and keep your entries together.
      </p>
      <form class="mt-4 space-y-4" @submit.prevent="claimAccount">
        <div>
          <label for="claim-email" class="block text-sm font-semibold text-ink">Email</label>
          <input
            id="claim-email"
            v-model="claimEmail"
            type="email"
            required
            autocomplete="email"
            class="mt-2 block w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div>
          <label for="claim-password" class="block text-sm font-semibold text-ink">Password</label>
          <input
            id="claim-password"
            v-model="claimPassword"
            type="password"
            required
            minlength="8"
            autocomplete="new-password"
            class="mt-2 block w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <button
          type="submit"
          :disabled="busy"
          class="w-full rounded-xl bg-primary px-4 py-3 font-semibold text-white hover:bg-primary-dark disabled:opacity-50"
        >
          Save
        </button>
      </form>
    </section>

    <!-- Passkeys -->
    <section class="mt-6 rounded-2xl border border-line bg-surface p-6 shadow-sm">
      <h2 class="text-lg font-semibold text-ink">Passkeys</h2>
      <div v-if="user?.needs_passkey" class="mt-3 rounded-xl bg-warn-bg px-4 py-3 text-sm text-warn">
        Family accounts sign in with a passkey. Add one on this device to continue.
      </div>
      <p v-else class="mt-1 text-sm text-muted">
        Sign in with your face, fingerprint or device PIN instead of a password.
        <template v-if="user?.role === 'family'">Required for family accounts.</template>
        <template v-else>Optional.</template>
      </p>

      <ul v-if="passkeys.length" class="mt-4 divide-y divide-line rounded-xl border border-line">
        <li v-for="passkey in passkeys" :key="passkey.id" class="flex items-center justify-between gap-3 px-4 py-3">
          <div class="min-w-0">
            <p class="truncate text-sm font-medium text-ink">{{ passkey.name }}</p>
            <p class="text-xs text-muted">Last used {{ formatDate(passkey.last_used_at) }}</p>
          </div>
          <button
            type="button"
            :disabled="busy"
            class="rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:bg-warn-bg hover:text-warn disabled:opacity-50"
            @click="removePasskey(passkey)"
          >
            Remove
          </button>
        </li>
      </ul>

      <p v-if="!canUsePasskey" class="mt-4 text-sm text-warn">
        This browser doesn't support passkeys. Try Safari, Chrome or Edge on an up-to-date device.
      </p>
      <form v-else class="mt-4 flex flex-col gap-3 sm:flex-row" @submit.prevent="addPasskey">
        <input
          v-model="newPasskeyName"
          type="text"
          maxlength="100"
          placeholder="Name it, e.g. My iPhone"
          aria-label="Passkey name"
          class="block w-full flex-1 rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <button
          type="submit"
          :disabled="busy"
          class="rounded-xl bg-primary px-4 py-3 font-semibold text-white hover:bg-primary-dark disabled:opacity-50"
        >
          Add a passkey
        </button>
      </form>
    </section>

    <!-- Password -->
    <section
      v-if="user?.has_password !== false"
      class="mt-6 rounded-2xl border border-line bg-surface p-6 shadow-sm"
    >
      <h2 class="text-lg font-semibold text-ink">Password</h2>
      <template v-if="passkeys.length">
        <p class="mt-1 text-sm text-muted">You'll confirm the change with one of your passkeys.</p>
        <form class="mt-4 flex flex-col gap-3 sm:flex-row" @submit.prevent="submitNewPassword">
          <input
            v-model="newPassword"
            type="password"
            required
            minlength="8"
            autocomplete="new-password"
            placeholder="New password"
            aria-label="New password"
            class="block w-full flex-1 rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <button
            type="submit"
            :disabled="busy"
            class="rounded-xl border border-line bg-white px-4 py-3 font-semibold text-ink hover:bg-paper disabled:opacity-50"
          >
            Change password
          </button>
        </form>
      </template>
      <p v-else class="mt-1 text-sm text-muted">
        To change your password, add a passkey first, or ask the family to reset it for you.
      </p>
    </section>

    <!-- Admin -->
    <section v-if="authStore.isFamily" class="mt-6 rounded-2xl border border-line bg-surface p-6 shadow-sm">
      <h2 class="text-lg font-semibold text-ink">Admin</h2>
      <p class="mt-1 text-sm text-muted">Manage accounts, reset passwords and remove lost passkeys.</p>
      <button
        type="button"
        :disabled="busy"
        class="mt-4 rounded-xl border border-line bg-white px-4 py-3 font-semibold text-ink hover:bg-paper disabled:opacity-50"
        @click="goToAdmin"
      >
        Open admin
      </button>
    </section>
  </div>
</template>
