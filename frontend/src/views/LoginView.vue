<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { isPasskeyCancel, passkeysSupported } from '@/services/passkeys'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const canUsePasskey = passkeysSupported()

function goToNext() {
  const redirect = route.query.redirect
  router.push(typeof redirect === 'string' ? redirect : '/dashboard')
}

function detailOf(error: unknown): { detail?: string; code?: string } {
  return (error as { response?: { data?: { detail?: string; code?: string } } })?.response?.data ?? {}
}

async function handleSubmit() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    await authStore.login({ email: email.value, password: password.value })
    goToNext()
  } catch (error: unknown) {
    const data = detailOf(error)
    if (data.code === 'passkey_required') {
      errorMessage.value = 'This account signs in with a passkey. Use the passkey button below.'
    } else if (error && typeof error === 'object' && 'response' in error) {
      errorMessage.value = data.detail || 'Invalid email or password'
    } else {
      errorMessage.value = 'Login failed. Please try again.'
    }
  } finally {
    isLoading.value = false
  }
}

async function handlePasskey() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    await authStore.loginWithPasskey()
    goToNext()
  } catch (error: unknown) {
    if (!isPasskeyCancel(error)) {
      errorMessage.value = detailOf(error).detail || "That passkey didn't work. Please try again."
    }
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-paper px-4 py-12 sm:px-6">
    <div class="mx-auto max-w-md">
      <p class="text-xs font-semibold uppercase tracking-wide text-muted">Private family page</p>
      <h1 class="mt-2 font-display text-4xl font-semibold leading-tight text-ink">Sign in</h1>
      <p class="mt-3 text-muted">
        New here? Open the invite link the family sent you to create your account.
      </p>

      <div class="mt-8 rounded-2xl border border-line bg-surface p-6 shadow-sm">
        <button
          v-if="canUsePasskey"
          type="button"
          :disabled="isLoading"
          class="w-full rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
          @click="handlePasskey"
        >
          Sign in with a passkey
        </button>

        <div v-if="canUsePasskey" class="my-6 flex items-center gap-3 text-xs uppercase tracking-wide text-muted">
          <span class="h-px flex-1 bg-line" />
          or use your password
          <span class="h-px flex-1 bg-line" />
        </div>

        <form @submit.prevent="handleSubmit">
          <label for="email-address" class="block text-sm font-semibold text-ink">Email</label>
          <input
            id="email-address"
            v-model="email"
            type="email"
            required
            autocomplete="username webauthn"
            class="mt-2 block w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />

          <label for="password" class="mt-5 block text-sm font-semibold text-ink">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            required
            autocomplete="current-password"
            class="mt-2 block w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />

          <div v-if="errorMessage" class="mt-4 rounded-xl bg-warn-bg p-4" role="alert">
            <p class="text-sm text-warn">{{ errorMessage }}</p>
          </div>

          <button
            type="submit"
            :disabled="isLoading"
            class="mt-6 w-full rounded-xl border border-line bg-white px-4 py-3 text-base font-semibold text-ink hover:bg-paper disabled:cursor-not-allowed disabled:opacity-50"
          >
            {{ isLoading ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>
      </div>

      <p class="mt-4 text-center text-sm text-muted">
        Forgot your password? Ask the family to reset it.
      </p>
    </div>
  </div>
</template>
