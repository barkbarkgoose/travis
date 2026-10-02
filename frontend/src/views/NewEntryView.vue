<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AuthImage from '@/components/journal/AuthImage.vue'
import {
  ADDITIONAL_NOTES_GUIDANCE,
  ADDITIONAL_NOTES_LABEL,
  PAIN_SOURCE_OPTIONS,
  PHOTO_NOTES_GUIDANCE,
  QUESTIONNAIRE_STEPS,
  TREND_OPTIONS
} from '@/config/questionnaire'
import * as journalApi from '@/services/journal'
import type { EntryAnswers, EntryWritePayload, PainSource, Photo, Trend } from '@/types/journal'
import { debounce } from '@/utils/debounce'

const router = useRouter()

function extractErrorMessage(err: unknown): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data
  if (typeof data?.detail === 'string') return data.detail
  if (data) {
    const firstKey = Object.keys(data)[0]
    const value = firstKey ? data[firstKey] : undefined
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  }
  return ''
}

function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// --- Draft lifecycle -------------------------------------------------------

const entryId = ref<number | null>(null)
const creating = ref(true)
const createError = ref('')

onMounted(async () => {
  try {
    const entry = await journalApi.createDraftEntry({ occurred_at: new Date().toISOString() })
    entryId.value = entry.id
    occurredAtLocal.value = toDatetimeLocalValue(new Date(entry.occurred_at))
  } catch (err) {
    createError.value = extractErrorMessage(err) || "Couldn't start a new entry. Please try again."
  } finally {
    creating.value = false
  }
})

// --- Form state --------------------------------------------------------

const occurredAtLocal = ref(toDatetimeLocalValue(new Date()))
const whoElseWasThere = ref('')
const overallNote = ref('')
const alertnessMood = ref('')
const painLevel = ref<number | null>(null)
const painSource = ref<PainSource | ''>('')
const trend = ref<Trend | ''>('')
const photoNotes = ref('')
const additionalNotes = ref('')

const answers = computed<EntryAnswers>(() => ({
  who_else_was_there: whoElseWasThere.value,
  overall_note: overallNote.value,
  alertness_mood: alertnessMood.value,
  photo_notes: photoNotes.value,
  additional_notes: additionalNotes.value
}))

const writePayload = computed<EntryWritePayload>(() => ({
  occurred_at: occurredAtLocal.value ? new Date(occurredAtLocal.value).toISOString() : undefined,
  pain_level: painLevel.value,
  pain_source: painSource.value,
  trend: trend.value,
  answers: answers.value
}))

// --- Autosave ------------------------------------------------------------

const saveState = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')

async function saveNow() {
  if (!entryId.value) return
  saveState.value = 'saving'
  try {
    await journalApi.updateEntry(entryId.value, writePayload.value)
    saveState.value = 'saved'
  } catch {
    saveState.value = 'error'
  }
}

const debouncedSave = debounce(saveNow, 1000)

watch(
  writePayload,
  () => {
    if (!entryId.value) return
    saveState.value = 'saving'
    debouncedSave()
  },
  { deep: true }
)

// --- Steps -----------------------------------------------------------------

const stepIndex = ref(0)
const steps = QUESTIONNAIRE_STEPS
const currentStep = computed(() => steps[stepIndex.value])
const isFirstStep = computed(() => stepIndex.value === 0)
const isLastStep = computed(() => stepIndex.value === steps.length - 1)

function goNext() {
  debouncedSave.cancel()
  void saveNow()
  if (!isLastStep.value) stepIndex.value += 1
}

function goBack() {
  debouncedSave.cancel()
  void saveNow()
  if (!isFirstStep.value) stepIndex.value -= 1
}

// --- Photos ------------------------------------------------------------

const photos = ref<Photo[]>([])
const uploading = ref(false)
const photoUploadError = ref('')

async function onFilesChosen(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || !files.length || !entryId.value) return

  uploading.value = true
  photoUploadError.value = ''
  for (const file of Array.from(files)) {
    try {
      const photo = await journalApi.uploadPhoto(entryId.value, file)
      photos.value.push(photo)
    } catch (err) {
      photoUploadError.value = extractErrorMessage(err) || `Couldn't upload ${file.name}.`
    }
  }
  uploading.value = false
  input.value = ''
}

// --- Submit ------------------------------------------------------------

const submitting = ref(false)
const submitError = ref('')

const canSubmit = computed(() => photoNotes.value.trim().length > 0)

async function handleSubmit() {
  if (!entryId.value || !canSubmit.value) return
  submitting.value = true
  submitError.value = ''
  debouncedSave.cancel()
  try {
    await saveNow()
    await journalApi.submitEntry(entryId.value)
    router.push({ name: 'my-entries', query: { submitted: String(entryId.value) } })
  } catch (err) {
    submitError.value = extractErrorMessage(err) || 'Could not submit. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl px-4 py-8 sm:px-6">
    <div v-if="creating" class="py-20 text-center text-muted">Starting a new entry…</div>

    <div v-else-if="createError" class="rounded-xl bg-warn-bg p-5 text-warn">
      {{ createError }}
    </div>

    <template v-else>
      <!-- Progress -->
      <div class="flex items-center justify-between">
        <p class="text-xs font-semibold uppercase tracking-wide text-muted">
          Step {{ stepIndex + 1 }} of {{ steps.length }}
        </p>
        <p class="text-xs text-muted">
          <span v-if="saveState === 'saving'">Saving…</span>
          <span v-else-if="saveState === 'saved'">Saved</span>
          <span v-else-if="saveState === 'error'" class="text-warn">Not saved — check your connection</span>
        </p>
      </div>
      <div class="mt-2 flex gap-1">
        <div
          v-for="(step, i) in steps"
          :key="step.id"
          class="h-1 flex-1 rounded-full"
          :class="i <= stepIndex ? 'bg-primary' : 'bg-line'"
        />
      </div>

      <h1 class="mt-5 font-display text-2xl font-semibold text-ink sm:text-3xl">
        {{ currentStep.title }}
      </h1>
      <p v-if="currentStep.guidance" class="mt-2 text-sm text-muted">{{ currentStep.guidance }}</p>

      <div class="mt-6 space-y-5">
        <!-- Step: visit -->
        <template v-if="currentStep.id === 'visit'">
          <div>
            <label for="occurred-at" class="block text-sm font-semibold text-ink">When was this visit?</label>
            <input
              id="occurred-at"
              v-model="occurredAtLocal"
              type="datetime-local"
              class="mt-2 w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <label for="who-else" class="block text-sm font-semibold text-ink">Who else was there?</label>
            <input
              id="who-else"
              v-model="whoElseWasThere"
              type="text"
              placeholder="e.g. Mom, Uncle Dave"
              class="mt-2 w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
        </template>

        <!-- Step: overall -->
        <template v-else-if="currentStep.id === 'overall'">
          <div>
            <label for="overall-note" class="block text-sm font-semibold text-ink">
              How is he doing overall?
            </label>
            <textarea
              id="overall-note"
              v-model="overallNote"
              rows="3"
              class="mt-2 w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <label for="mood" class="block text-sm font-semibold text-ink">Alertness / mood</label>
            <input
              id="mood"
              v-model="alertnessMood"
              type="text"
              class="mt-2 w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <span class="block text-sm font-semibold text-ink">Pain level (0–10)</span>
            <div class="mt-2 flex items-center gap-4">
              <input
                v-model.number="painLevel"
                type="range"
                min="0"
                max="10"
                step="1"
                class="w-full accent-primary"
              />
              <span class="w-8 text-center font-mono text-lg text-ink">{{ painLevel ?? '—' }}</span>
            </div>
            <button
              v-if="painLevel !== null"
              type="button"
              class="mt-1 text-xs text-muted underline"
              @click="painLevel = null"
            >
              Clear
            </button>
          </div>
          <div v-if="painLevel !== null">
            <span class="block text-sm font-semibold text-ink">Where did that number come from?</span>
            <div class="mt-2 flex flex-wrap gap-2">
              <button
                v-for="opt in PAIN_SOURCE_OPTIONS"
                :key="opt.value"
                type="button"
                class="rounded-full border px-4 py-2 text-sm font-medium"
                :class="
                  painSource === opt.value
                    ? 'border-primary bg-primary text-white'
                    : 'border-line bg-white text-ink'
                "
                @click="painSource = opt.value"
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
                class="rounded-full border px-4 py-2 text-sm font-medium"
                :class="
                  trend === opt.value ? 'border-primary bg-primary text-white' : 'border-line bg-white text-ink'
                "
                @click="trend = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
        </template>

        <!-- Step: photos & notes -->
        <template v-else-if="currentStep.id === 'photos'">
          <div>
            <div class="flex flex-wrap gap-3">
              <AuthImage
                v-for="photo in photos"
                :key="photo.id"
                :src="photo.urls.thumb"
                alt="Uploaded photo"
                class="h-20 w-20 rounded-lg object-cover"
              />
            </div>

            <label
              class="mt-3 inline-flex cursor-pointer items-center gap-2 rounded-xl border border-line bg-paper px-4 py-2 text-sm font-medium text-ink hover:bg-white"
            >
              <span v-if="uploading">Uploading…</span>
              <span v-else>{{ photos.length ? 'Add another photo' : 'Add photo' }}</span>
              <input
                type="file"
                accept="image/*"
                multiple
                class="hidden"
                :disabled="uploading"
                @change="onFilesChosen"
              />
            </label>
            <p v-if="photoUploadError" class="mt-2 text-sm text-warn">{{ photoUploadError }}</p>
          </div>

          <div>
            <label for="photo-notes" class="block text-sm font-semibold text-ink">
              {{ PHOTO_NOTES_GUIDANCE }}
              <span class="font-normal text-muted">(required)</span>
            </label>
            <textarea
              id="photo-notes"
              v-model="photoNotes"
              rows="3"
              placeholder="e.g. Bruising on his left forearm looks about the same as yesterday."
              class="mt-2 w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>

          <div>
            <label for="additional-notes" class="block text-sm font-semibold text-ink">
              {{ ADDITIONAL_NOTES_LABEL }}
            </label>
            <p class="mt-1 text-xs text-muted">{{ ADDITIONAL_NOTES_GUIDANCE }}</p>
            <textarea
              id="additional-notes"
              v-model="additionalNotes"
              rows="5"
              class="mt-2 w-full rounded-xl border border-line bg-white px-4 py-3 text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>

          <p v-if="!canSubmit" class="text-sm text-warn">Add a note on the photos above before submitting.</p>
          <p v-if="submitError" class="rounded-xl bg-warn-bg p-4 text-sm text-warn">{{ submitError }}</p>
        </template>
      </div>

      <!-- Nav -->
      <div class="mt-8 flex items-center justify-between border-t border-line pt-5">
        <button
          type="button"
          class="rounded-xl px-4 py-2 text-sm font-medium text-muted disabled:opacity-40"
          :disabled="isFirstStep"
          @click="goBack"
        >
          Back
        </button>

        <button
          v-if="!isLastStep"
          type="button"
          class="rounded-xl bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-dark"
          @click="goNext"
        >
          Next
        </button>
        <button
          v-else
          type="button"
          :disabled="submitting || !canSubmit"
          class="rounded-xl bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
          @click="handleSubmit"
        >
          {{ submitting ? 'Submitting…' : 'Submit entry' }}
        </button>
      </div>
    </template>
  </div>
</template>
