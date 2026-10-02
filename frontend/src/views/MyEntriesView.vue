<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as journalApi from '@/services/journal'
import { useAuthStore } from '@/stores/auth'
import type { Entry } from '@/types/journal'
import { extractErrorMessage } from '@/utils/apiError'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const entries = ref<Entry[]>([])
const loading = ref(true)
const loadError = ref('')
const showEveryone = ref(false)

// Drafts pile up (every "Log a visit" starts a fresh one), so a visitor can
// discard their own unfinished ones. Submitted entries can't be deleted at
// all — the server rejects that — so no such control shows for those.
const confirmingDeleteId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const deleteError = ref('')

async function handleDelete(id: number) {
  deletingId.value = id
  deleteError.value = ''
  try {
    await journalApi.deleteEntry(id)
    entries.value = entries.value.filter((e) => e.id !== id)
    confirmingDeleteId.value = null
  } catch (err) {
    deleteError.value = extractErrorMessage(err) || "Couldn't delete that draft. Please try again."
  } finally {
    deletingId.value = null
  }
}

const justSubmittedId = computed(() => {
  const value = route.query.submitted
  return typeof value === 'string' ? Number(value) : null
})

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    entries.value = await journalApi.listEntries({ all: showEveryone.value })
  } catch {
    loadError.value = "Couldn't load entries. Please try again."
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(showEveryone, load)

function dismissBanner() {
  router.replace({ query: {} })
}
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="font-display text-3xl font-semibold text-ink">
        {{ showEveryone ? "Everyone's entries" : 'My entries' }}
      </h1>
      <router-link
        to="/entries/new"
        class="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark"
      >
        Log a visit
      </router-link>
    </div>

    <label v-if="authStore.isFamily" class="mt-3 inline-flex items-center gap-2 text-sm text-muted">
      <input v-model="showEveryone" type="checkbox" class="accent-primary" />
      Show everyone's entries
    </label>

    <div
      v-if="justSubmittedId"
      class="mt-5 flex items-center justify-between rounded-xl bg-ok-bg px-4 py-3 text-sm text-ok"
    >
      <span>Entry submitted. Thank you for writing it down.</span>
      <button type="button" class="font-semibold underline" @click="dismissBanner">Dismiss</button>
    </div>

    <div v-if="loading" class="py-16 text-center text-muted">Loading…</div>
    <div v-else-if="loadError" class="mt-6 rounded-xl bg-warn-bg p-4 text-warn">{{ loadError }}</div>
    <div v-else-if="entries.length === 0" class="mt-10 text-center text-muted">
      No entries yet.
      <router-link to="/entries/new" class="font-semibold text-primary">Log the first one.</router-link>
    </div>

    <template v-else>
      <p v-if="deleteError" class="mt-4 rounded-xl bg-warn-bg p-3 text-sm text-warn">{{ deleteError }}</p>

      <ul class="mt-6 space-y-3">
        <li v-for="entry in entries" :key="entry.id">
          <router-link
            :to="`/entries/${entry.id}`"
            class="block rounded-2xl border border-line bg-surface p-4 shadow-sm hover:border-primary"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span class="font-display text-lg font-semibold text-ink">
                {{ new Date(entry.occurred_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }}
              </span>
              <span
                class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                :class="entry.status === 'submitted' ? 'bg-ok-bg text-ok' : 'bg-line text-muted'"
              >
                {{ entry.status === 'submitted' ? 'Submitted' : 'Draft' }}
              </span>
            </div>
            <p v-if="showEveryone" class="mt-1 text-sm text-muted">By {{ entry.author_name }}</p>
            <p class="mt-2 text-sm text-muted">
              <span v-if="entry.pain_level !== null">Pain {{ entry.pain_level }}/10 · </span>
              {{ entry.photos.length }} photo{{ entry.photos.length === 1 ? '' : 's' }}
            </p>
          </router-link>

          <!-- Only a draft's own author can discard it — the server rejects
               anything else, so there's nothing to show otherwise. -->
          <div v-if="entry.status === 'draft' && entry.can_edit" class="mt-1.5 flex justify-end">
            <span v-if="confirmingDeleteId === entry.id" class="inline-flex items-center gap-2 text-xs text-warn">
              Delete this draft?
              <button
                type="button"
                class="font-semibold underline disabled:opacity-50"
                :disabled="deletingId === entry.id"
                @click="handleDelete(entry.id)"
              >
                {{ deletingId === entry.id ? 'Deleting…' : 'Yes' }}
              </button>
              <button type="button" class="underline" @click="confirmingDeleteId = null">No</button>
            </span>
            <button
              v-else
              type="button"
              class="text-xs font-medium text-muted hover:text-warn"
              @click="confirmingDeleteId = entry.id"
            >
              Delete draft
            </button>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>
