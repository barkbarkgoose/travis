<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import * as visitsApi from '@/services/visits'
import { useAuthStore } from '@/stores/auth'
import type { Visit } from '@/types/visits'

const authStore = useAuthStore()

const firstName = computed(() => authStore.user?.name?.split(' ')[0] ?? '')

// "Visiting today" widget — a lightweight stand-in for a dedicated Today
// view, since this dashboard already is the landing page.
const visitsToday = ref<Visit[]>([])
const visitsLoaded = ref(false)

const rightNow = computed(() => {
  const now = new Date()
  return visitsToday.value.filter(
    (v) => v.status === 'planned' && v.kind === 'visit' && new Date(v.start) <= now && new Date(v.end) > now
  )
})

const upcomingToday = computed(() => {
  const now = new Date()
  return visitsToday.value
    .filter((v) => v.status === 'planned' && v.kind === 'visit' && new Date(v.start) > now)
    .slice(0, 3)
})

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

async function loadVisitsToday() {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const end = new Date(start)
  end.setDate(end.getDate() + 1)
  try {
    visitsToday.value = await visitsApi.listVisits(start, end)
  } catch {
    // Non-critical widget — the full calendar link still works either way.
  } finally {
    visitsLoaded.value = true
  }
}

// Family-only: the shared join link.
const inviteToken = ref<string | null>(null)
const inviteLoaded = ref(false)
const confirmingRotate = ref(false)
const copied = ref(false)

const inviteUrl = computed(() =>
  inviteToken.value ? `${window.location.origin}/join/${inviteToken.value}` : ''
)

async function loadInvite() {
  const { data } = await api.get<{ token: string | null }>('/api/v1/auth/invite/')
  inviteToken.value = data.token
  inviteLoaded.value = true
}

async function rotateInvite() {
  const { data } = await api.post<{ token: string }>('/api/v1/auth/invite/')
  inviteToken.value = data.token
  confirmingRotate.value = false
}

async function copyInvite() {
  try {
    await navigator.clipboard.writeText(inviteUrl.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    // Clipboard can be blocked; the link is visible and selectable anyway.
  }
}

onMounted(() => {
  if (authStore.isFamily) void loadInvite()
  void loadVisitsToday()
})
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-10 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-ink">Hi, {{ firstName }}</h1>
    <p class="mt-2 text-muted">
      Just visited? Log what you saw while it's fresh — notes, pain level, and any photos.
    </p>

    <div class="mt-6 flex flex-wrap gap-3">
      <router-link
        to="/entries/new"
        class="rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-primary-dark"
      >
        Log a visit
      </router-link>
      <router-link
        to="/entries"
        class="rounded-xl border border-line bg-surface px-5 py-3 text-sm font-semibold text-ink hover:bg-white"
      >
        My entries
      </router-link>
      <router-link
        to="/calendar"
        class="rounded-xl border border-line bg-surface px-5 py-3 text-sm font-semibold text-ink hover:bg-white"
      >
        Calendar
      </router-link>
    </div>

    <section class="mt-8 rounded-2xl border border-line bg-surface p-6 shadow-sm">
      <div class="flex items-center justify-between">
        <h2 class="font-display text-xl font-semibold text-ink">Visiting today</h2>
        <router-link to="/calendar" class="text-sm font-semibold text-primary hover:underline">
          Full calendar →
        </router-link>
      </div>

      <template v-if="visitsLoaded">
        <div class="mt-4">
          <p class="text-xs font-semibold uppercase tracking-wide text-muted">Right now</p>
          <p v-if="!rightNow.length" class="mt-1 text-sm text-muted">No one's visiting at the moment.</p>
          <ul v-else class="mt-1 space-y-1">
            <li v-for="v in rightNow" :key="v.id" class="text-sm text-ink">
              {{ v.user_name }}<span v-if="v.note" class="text-muted"> · {{ v.note }}</span>
            </li>
          </ul>
        </div>
        <div class="mt-4">
          <p class="text-xs font-semibold uppercase tracking-wide text-muted">Coming up today</p>
          <p v-if="!upcomingToday.length" class="mt-1 text-sm text-muted">Nothing else booked today.</p>
          <ul v-else class="mt-1 space-y-1">
            <li v-for="v in upcomingToday" :key="v.id" class="text-sm text-ink">
              {{ formatTime(v.start) }} · {{ v.user_name }}<span v-if="v.note" class="text-muted"> · {{ v.note }}</span>
            </li>
          </ul>
        </div>
      </template>
    </section>

    <section
      v-if="authStore.isFamily"
      class="mt-8 rounded-2xl border border-line bg-surface p-6 shadow-sm"
    >
      <h2 class="font-display text-xl font-semibold text-ink">Invite link for visitors</h2>
      <p class="mt-1 text-sm text-muted">
        Anyone with this link can join and add notes and photos. If it gets shared too widely,
        make a new one. The old one stops working immediately (people already joined stay signed in).
      </p>

      <template v-if="inviteLoaded">
        <div v-if="inviteToken" class="mt-4">
          <input
            :value="inviteUrl"
            readonly
            aria-label="Invite link"
            class="w-full rounded-xl border border-line bg-paper px-3 py-2 font-mono text-sm text-ink"
            @focus="($event.target as HTMLInputElement).select()"
          />
          <button
            type="button"
            class="mt-3 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark"
            @click="copyInvite"
          >
            {{ copied ? 'Copied' : 'Copy link' }}
          </button>
        </div>
        <p v-else class="mt-4 text-sm text-muted">No active link yet.</p>

        <div class="mt-4 border-t border-line pt-4">
          <button
            v-if="!confirmingRotate"
            type="button"
            class="text-sm font-medium text-warn hover:underline"
            @click="confirmingRotate = true"
          >
            {{ inviteToken ? 'Make a new link…' : 'Create a link' }}
          </button>
          <div v-else class="flex flex-wrap items-center gap-3">
            <span class="text-sm text-ink">The current link will stop working. Continue?</span>
            <button
              type="button"
              class="rounded-xl bg-warn px-3 py-1.5 text-sm font-semibold text-white"
              @click="rotateInvite"
            >
              Yes, replace it
            </button>
            <button type="button" class="text-sm text-muted" @click="confirmingRotate = false">
              Cancel
            </button>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>
