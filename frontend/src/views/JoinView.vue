<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const token = computed(() => String(route.params.token ?? ''))
const fullName = ref('')
const email = ref('')
const password = ref('')
const isLoading = ref(false)
const errorMessage = ref('')

// Tapping the link again on a phone that's already signed in must not create a
// second account: attribution of notes and photos depends on one name per person.
// On a new device, people sign in with their email and password instead.
const alreadySignedIn = ref(authStore.isAuthenticated)

function continueAsCurrent() {
  router.push('/dashboard')
}

function joinAsSomeoneElse() {
  authStore.logout()
  alreadySignedIn.value = false
}

async function handleSubmit() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    await authStore.join({
      token: token.value,
      full_name: fullName.value,
      email: email.value,
      password: password.value
    })
    router.push('/dashboard')
  } catch (error: unknown) {
    const data = (error as { response?: { data?: Record<string, unknown> } })?.response?.data
    const firstError = (field: string) =>
      Array.isArray(data?.[field]) ? String((data?.[field] as unknown[])[0]) : ''
    errorMessage.value =
      firstError('full_name') ||
      firstError('email') ||
      firstError('password') ||
      (typeof data?.detail === 'string' ? data.detail : '') ||
      'Something went wrong. Please try again.'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-paper px-4 py-12 sm:px-6">
    <div class="mx-auto max-w-md">
      <p class="text-xs font-semibold uppercase tracking-wide text-muted">Private family page</p>
      <h1 class="mt-2 font-display text-4xl font-semibold leading-tight text-ink">
        Travis's Recovery
      </h1>

      <div v-if="alreadySignedIn" class="mt-8 rounded-2xl border border-line bg-surface p-6 shadow-sm">
        <p class="text-ink">
          You're already signed in as
          <strong>{{ authStore.user?.name }}</strong>.
        </p>
        <button
          type="button"
          class="mt-5 w-full rounded-xl bg-primary px-4 py-3 font-semibold text-white hover:bg-primary-dark"
          @click="continueAsCurrent"
        >
          Continue
        </button>
        <button
          type="button"
          class="mt-3 w-full rounded-xl px-4 py-3 text-sm font-medium text-muted hover:text-ink"
          @click="joinAsSomeoneElse"
        >
          I'm someone else
        </button>
      </div>

      <form
        v-else
        class="mt-8 rounded-2xl border border-line bg-surface p-6 shadow-sm"
        @submit.prevent="handleSubmit"
      >
        <p class="text-muted">
          This is where family and friends log what they see during a visit and book visiting times.
        </p>

        <label for="full-name" class="mt-6 block text-sm font-semibold text-ink">
          Your first and last name
        </label>
        <input
          id="full-name"
          v-model="fullName"
          type="text"
          required
          autocomplete="name"
          autocapitalize="words"
          class="mt-2 block w-full rounded-xl border border-line bg-white px-4 py-3 text-lg text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          placeholder="e.g. Maria Lopez"
        />
        <p class="mt-2 text-sm text-muted">
          Your full name is saved with everything you write or photograph, so the family can tell
          who saw what.
        </p>

        <label for="email-address" class="mt-6 block text-sm font-semibold text-ink">Email</label>
        <input
          id="email-address"
          v-model="email"
          type="email"
          required
          autocomplete="email"
          class="mt-2 block w-full rounded-xl border border-line bg-white px-4 py-3 text-lg text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        />

        <label for="new-password" class="mt-6 block text-sm font-semibold text-ink">
          Choose a password
        </label>
        <input
          id="new-password"
          v-model="password"
          type="password"
          required
          minlength="8"
          autocomplete="new-password"
          class="mt-2 block w-full rounded-xl border border-line bg-white px-4 py-3 text-lg text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <p class="mt-2 text-sm text-muted">
          At least 8 characters. Use your email and this password to sign in on your other
          devices. You can add a passkey later for one-tap sign-in.
        </p>

        <div v-if="errorMessage" class="mt-4 rounded-xl bg-warn-bg p-4" role="alert">
          <p class="text-sm text-warn">{{ errorMessage }}</p>
        </div>

        <button
          type="submit"
          :disabled="isLoading"
          class="mt-6 w-full rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {{ isLoading ? 'Creating your account…' : 'Create account' }}
        </button>
      </form>

      <p v-if="!alreadySignedIn" class="mt-4 text-center text-sm text-muted">
        Already have an account?
        <router-link to="/login" class="font-semibold text-primary hover:text-primary-dark">
          Sign in
        </router-link>
      </p>
    </div>
  </div>
</template>
