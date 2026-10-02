<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthImage from '@/components/journal/AuthImage.vue'
import { PAIN_SOURCE_OPTIONS, TREND_OPTIONS } from '@/config/questionnaire'
import * as journalApi from '@/services/journal'
import type { Entry, EntryWritePayload, PainSource, Trend } from '@/types/journal'
import { extractErrorMessage } from '@/utils/apiError'

const route = useRoute()
const router = useRouter()
const entryId = Number(route.params.id)

const entry = ref<Entry | null>(null)
const loading = ref(true)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    entry.value = await journalApi.fetchEntry(entryId)
  } catch (err) {
    loadError.value = extractErrorMessage(err) || "Couldn't load this entry."
  } finally {
    loading.value = false
  }
}

onMounted(load)

function optionLabel(list: { value: string; label: string }[], value: string): string {
  return list.find((o) => o.value === value)?.label ?? value
}

const ANSWER_LABELS: [key: string, label: string][] = [
  ['who_else_was_there', 'Who else was there'],
  ['overall_note', 'Overall'],
  ['alertness_mood', 'Alertness / mood'],
  ['photo_notes', 'What the photos show'],
  ['additional_notes', 'Anything else']
]

const answerRows = computed(() => {
  if (!entry.value) return []
  const a = entry.value.answers as Record<string, unknown>
  return ANSWER_LABELS.filter(([key]) => a[key]).map(([key, label]) => ({
    key,
    label,
    value: String(a[key])
  }))
})

// --- Edit mode ---------------------------------------------------------

const editing = ref(false)
const saving = ref(false)
const saveError = ref('')

const editOccurredAt = ref('')
const editPainLevel = ref<number | null>(null)
const editPainSource = ref<PainSource | ''>('')
const editTrend = ref<Trend | ''>('')
const editAnswers = reactive<Record<string, string>>({})

function toDatetimeLocalValue(iso: string): string {
  const date = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function startEditing() {
  if (!entry.value) return
  editOccurredAt.value = toDatetimeLocalValue(entry.value.occurred_at)
  editPainLevel.value = entry.value.pain_level
  editPainSource.value = entry.value.pain_source
  editTrend.value = entry.value.trend
  const a = entry.value.answers as Record<string, unknown>
  for (const [key] of ANSWER_LABELS) {
    editAnswers[key] = String(a[key] ?? '')
  }
  saveError.value = ''
  editing.value = true
}

async function saveEdits() {
  if (!entry.value) return
  saving.value = true
  saveError.value = ''
  const payload: EntryWritePayload = {
    occurred_at: new Date(editOccurredAt.value).toISOString(),
    pain_level: editPainLevel.value,
    pain_source: editPainSource.value,
    trend: editTrend.value,
    answers: { ...entry.value.answers, ...editAnswers }
  }
  try {
    entry.value = await journalApi.updateEntry(entryId, payload)
    editing.value = false
  } catch (err) {
    saveError.value = extractErrorMessage(err) || "Couldn't save your changes."
  } finally {
    saving.value = false
  }
}

// --- Delete draft ----------------------------------------------------------
// Drafts pile up (every "Log a visit" starts a fresh one), so a visitor can
// discard their own unfinished one from here too. The server rejects this
// once the entry is submitted, so the button only shows for a draft.

const confirmingDelete = ref(false)
const deleting = ref(false)
const deleteError = ref('')

async function handleDelete() {
  deleting.value = true
  deleteError.value = ''
  try {
    await journalApi.deleteEntry(entryId)
    router.push('/entries')
  } catch (err) {
    deleteError.value = extractErrorMessage(err) || "Couldn't delete that draft."
    deleting.value = false
  }
}

// --- Addenda -------------------------------------------------------------

const addendumBody = ref('')
const addingAddendum = ref(false)
const addendumError = ref('')

async function submitAddendum() {
  if (!addendumBody.value.trim() || !entry.value) return
  addingAddendum.value = true
  addendumError.value = ''
  try {
    const addendum = await journalApi.addAddendum(entryId, addendumBody.value.trim())
    entry.value.addenda.push(addendum)
    addendumBody.value = ''
  } catch (err) {
    addendumError.value = extractErrorMessage(err) || "Couldn't add that."
  } finally {
    addingAddendum.value = false
  }
}

// --- Add photos ----------------------------------------------------------

const uploadingPhoto = ref(false)
const photoUploadError = ref('')

async function onPhotoChosen(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || !files.length || !entry.value) return
  uploadingPhoto.value = true
  photoUploadError.value = ''
  for (const file of Array.from(files)) {
    try {
      const photo = await journalApi.uploadPhoto(entryId, file)
      entry.value.photos.push(photo)
    } catch (err) {
      photoUploadError.value = extractErrorMessage(err) || `Couldn't upload ${file.name}.`
    }
  }
  uploadingPhoto.value = false
  input.value = ''
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <router-link to="/entries" class="text-sm font-medium text-muted hover:text-ink">&larr; My entries</router-link>

    <div v-if="loading" class="py-16 text-center text-muted">Loading…</div>
    <div v-else-if="loadError" class="mt-6 rounded-xl bg-warn-bg p-4 text-warn">{{ loadError }}</div>

    <template v-else-if="entry">
      <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
        <h1 class="font-display text-2xl font-semibold text-ink sm:text-3xl">
          {{ new Date(entry.occurred_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }}
        </h1>
        <span
          class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
          :class="entry.status === 'submitted' ? 'bg-ok-bg text-ok' : 'bg-line text-muted'"
        >
          {{ entry.status === 'submitted' ? 'Submitted' : 'Draft' }}
        </span>
      </div>
      <p class="mt-1 text-sm text-muted">By {{ entry.author_name }}</p>

      <p v-if="entry.can_edit" class="mt-4 rounded-xl bg-paper p-3 text-sm text-muted">
        You can still edit this
        <template v-if="entry.edit_window_ends_at">
          until {{ new Date(entry.edit_window_ends_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }}
        </template>
        <template v-else>while it's a draft</template>.
        <button type="button" class="ml-1 font-semibold text-primary underline" @click="startEditing">
          Edit
        </button>
      </p>
      <p v-else-if="entry.is_locked" class="mt-4 rounded-xl bg-paper p-3 text-sm text-muted">
        This entry is locked. Add an addendum below instead of editing it.
      </p>

      <div v-if="entry.status === 'draft' && entry.can_edit" class="mt-2">
        <span v-if="confirmingDelete" class="inline-flex items-center gap-2 text-sm text-warn">
          Delete this draft? It can't be undone.
          <button
            type="button"
            class="font-semibold underline disabled:opacity-50"
            :disabled="deleting"
            @click="handleDelete"
          >
            {{ deleting ? 'Deleting…' : 'Yes, delete it' }}
          </button>
          <button type="button" class="underline" @click="confirmingDelete = false">No</button>
        </span>
        <button v-else type="button" class="text-sm font-medium text-muted hover:text-warn" @click="confirmingDelete = true">
          Delete draft
        </button>
        <p v-if="deleteError" class="mt-1 text-sm text-warn">{{ deleteError }}</p>
      </div>

      <!-- Edit form -->
      <div v-if="editing" class="mt-6 space-y-4 rounded-2xl border border-line bg-surface p-5">
        <div>
          <label class="block text-sm font-semibold text-ink">When</label>
          <input
            v-model="editOccurredAt"
            type="datetime-local"
            class="mt-2 w-full rounded-xl border border-line bg-white px-4 py-3 text-ink"
          />
        </div>
        <div>
          <span class="block text-sm font-semibold text-ink">Pain level (0–10)</span>
          <div class="mt-2 flex items-center gap-4">
            <input v-model.number="editPainLevel" type="range" min="0" max="10" step="1" class="w-full accent-primary" />
            <span class="w-8 text-center font-mono text-lg text-ink">{{ editPainLevel ?? '—' }}</span>
          </div>
          <div v-if="editPainLevel !== null" class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="opt in PAIN_SOURCE_OPTIONS"
              :key="opt.value"
              type="button"
              class="rounded-full border px-3 py-1.5 text-sm font-medium"
              :class="editPainSource === opt.value ? 'border-primary bg-primary text-white' : 'border-line bg-white text-ink'"
              @click="editPainSource = opt.value"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
        <div>
          <span class="block text-sm font-semibold text-ink">Compared to last visit</span>
          <div class="mt-2 flex flex-wrap gap-2">
            <button
              v-for="opt in TREND_OPTIONS"
              :key="opt.value"
              type="button"
              class="rounded-full border px-3 py-1.5 text-sm font-medium"
              :class="editTrend === opt.value ? 'border-primary bg-primary text-white' : 'border-line bg-white text-ink'"
              @click="editTrend = opt.value"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
        <div v-for="[key, label] in ANSWER_LABELS" :key="key">
          <label class="block text-sm font-semibold text-ink">{{ label }}</label>
          <textarea
            v-model="editAnswers[key]"
            rows="2"
            class="mt-2 w-full rounded-xl border border-line bg-white px-3 py-2 text-sm text-ink"
          />
        </div>

        <p v-if="saveError" class="text-sm text-warn">{{ saveError }}</p>

        <div class="flex gap-3">
          <button
            type="button"
            :disabled="saving"
            class="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-50"
            @click="saveEdits"
          >
            {{ saving ? 'Saving…' : 'Save changes' }}
          </button>
          <button type="button" class="text-sm text-muted" @click="editing = false">Cancel</button>
        </div>
      </div>

      <!-- Read view -->
      <template v-else>
        <div v-if="entry.pain_level !== null" class="mt-6 rounded-2xl border border-line bg-surface p-4">
          <p class="text-sm font-semibold text-ink">
            Pain: {{ entry.pain_level }}/10
            <span v-if="entry.pain_source" class="font-normal text-muted">
              ({{ optionLabel(PAIN_SOURCE_OPTIONS, entry.pain_source) }})
            </span>
          </p>
          <p v-if="entry.trend" class="mt-1 text-sm text-muted">{{ optionLabel(TREND_OPTIONS, entry.trend) }}</p>
        </div>

        <dl v-if="answerRows.length" class="mt-6 space-y-4">
          <div v-for="row in answerRows" :key="row.label">
            <dt class="text-xs font-semibold uppercase tracking-wide text-muted">{{ row.label }}</dt>
            <dd class="mt-1 whitespace-pre-wrap text-ink">{{ row.value }}</dd>
          </div>
        </dl>

        <div v-if="entry.photos.length" class="mt-6 flex flex-wrap gap-3">
          <AuthImage
            v-for="photo in entry.photos"
            :key="photo.id"
            :src="photo.urls.display"
            alt="Visit photo"
            class="h-32 w-32 rounded-xl object-cover"
          />
        </div>

        <div class="mt-6">
          <label class="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-line bg-paper px-4 py-2 text-sm font-medium text-ink hover:bg-white">
            <span v-if="uploadingPhoto">Uploading…</span>
            <span v-else>{{ entry.photos.length ? 'Add another photo' : 'Add photo' }}</span>
            <input type="file" accept="image/*" multiple class="hidden" :disabled="uploadingPhoto" @change="onPhotoChosen" />
          </label>
          <p v-if="photoUploadError" class="mt-2 text-sm text-warn">{{ photoUploadError }}</p>
        </div>
      </template>

      <!-- Addenda -->
      <div class="mt-8 border-t border-line pt-6">
        <h2 class="font-display text-lg font-semibold text-ink">Addenda</h2>
        <ul v-if="entry.addenda.length" class="mt-3 space-y-3">
          <li v-for="addendum in entry.addenda" :key="addendum.id" class="rounded-xl bg-paper p-3 text-sm">
            <p class="text-ink">{{ addendum.body }}</p>
            <p class="mt-1 text-xs text-muted">
              {{ addendum.author_name }} ·
              {{ new Date(addendum.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) }}
            </p>
          </li>
        </ul>

        <div class="mt-4">
          <textarea
            v-model="addendumBody"
            rows="2"
            placeholder="Add a dated correction or follow-up…"
            class="w-full rounded-xl border border-line bg-white px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <p v-if="addendumError" class="mt-1 text-sm text-warn">{{ addendumError }}</p>
          <button
            type="button"
            :disabled="addingAddendum || !addendumBody.trim()"
            class="mt-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-50"
            @click="submitAddendum"
          >
            {{ addingAddendum ? 'Adding…' : 'Add' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
