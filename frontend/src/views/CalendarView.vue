<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import * as visitsApi from '@/services/visits'
import { useAuthStore } from '@/stores/auth'
import type { Visit, VisitWritePayload } from '@/types/visits'
import { extractErrorMessage } from '@/utils/apiError'

const authStore = useAuthStore()

// Visiting hours aren't finalized yet (see the project plan's open questions) —
// 7am–9pm is a reasonable default any hour of which can be booked; narrow this
// once the hospital's actual hours are known.
const HOUR_START = 7
const HOUR_END = 21

function startOfDay(date: Date): Date {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy
}

function addDays(date: Date, n: number): Date {
  const copy = new Date(date)
  copy.setDate(copy.getDate() + n)
  return copy
}

function isSameDay(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString()
}

const today = startOfDay(new Date())
const days = Array.from({ length: 14 }, (_, i) => addDays(today, i))
const selectedDate = ref(today)

const visits = ref<Visit[]>([])
const loading = ref(true)
const loadError = ref('')

async function loadDay(date: Date) {
  loading.value = true
  loadError.value = ''
  try {
    visits.value = await visitsApi.listVisits(startOfDay(date), addDays(startOfDay(date), 1))
  } catch {
    loadError.value = "Couldn't load the calendar. Please try again."
  } finally {
    loading.value = false
  }
}

onMounted(() => loadDay(selectedDate.value))
watch(selectedDate, loadDay)

const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i)

function hourSlot(hour: number): { start: Date; end: Date } {
  const start = new Date(selectedDate.value)
  start.setHours(hour, 0, 0, 0)
  const end = new Date(start)
  end.setHours(end.getHours() + 1)
  return { start, end }
}

function formatHour(hour: number): string {
  const d = new Date()
  d.setHours(hour, 0, 0, 0)
  return d.toLocaleTimeString(undefined, { hour: 'numeric' })
}

interface RowInfo {
  blocked: Visit | undefined
  bookings: Visit[]
  isPast: boolean
}

function rowInfo(hour: number): RowInfo {
  const { start, end } = hourSlot(hour)
  const overlapping = visits.value.filter(
    (v) => v.status === 'planned' && new Date(v.start) < end && new Date(v.end) > start
  )
  return {
    blocked: overlapping.find((v) => v.kind === 'blocked'),
    bookings: overlapping.filter((v) => v.kind === 'visit'),
    isPast: end <= new Date()
  }
}

// --- Booking form --------------------------------------------------------

const openHour = ref<number | null>(null)
const bookingNote = ref('')
const bookingDurationMinutes = ref(60)
const blockMode = ref(false)
const submitting = ref(false)
const formError = ref('')

function openBookingForm(hour: number) {
  openHour.value = hour
  bookingNote.value = ''
  bookingDurationMinutes.value = 60
  blockMode.value = false
  formError.value = ''
}

function closeBookingForm() {
  openHour.value = null
}

async function submitBooking(hour: number) {
  const { start } = hourSlot(hour)
  const end = new Date(start)
  end.setMinutes(end.getMinutes() + bookingDurationMinutes.value)

  submitting.value = true
  formError.value = ''
  try {
    const payload: VisitWritePayload = {
      start: start.toISOString(),
      end: end.toISOString(),
      note: bookingNote.value.trim()
    }
    if (blockMode.value && authStore.isFamily) payload.kind = 'blocked'
    await visitsApi.createVisit(payload)
    closeBookingForm()
    await loadDay(selectedDate.value)
  } catch (err) {
    formError.value = extractErrorMessage(err) || "Couldn't book that time. Please try again."
  } finally {
    submitting.value = false
  }
}

// --- Cancel ----------------------------------------------------------------

const confirmingCancelId = ref<number | null>(null)
const cancelling = ref(false)
const cancelError = ref('')

async function handleCancel(id: number) {
  cancelling.value = true
  cancelError.value = ''
  try {
    await visitsApi.cancelVisit(id)
    confirmingCancelId.value = null
    await loadDay(selectedDate.value)
  } catch (err) {
    cancelError.value = extractErrorMessage(err) || "Couldn't cancel that booking. Please try again."
  } finally {
    cancelling.value = false
  }
}

const dayHeading = computed(() =>
  selectedDate.value.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric'
  })
)
</script>

<template>
  <div class="mx-auto max-w-3xl px-4 py-8 sm:px-6">
    <h1 class="font-display text-3xl font-semibold text-ink">Visit calendar</h1>
    <p class="mt-2 text-sm text-muted">
      Pick a day, then a time. Up to a few visitors can overlap — if a time's full or blocked,
      you'll see why when you try to book it.
    </p>

    <!-- Date strip -->
    <div class="date-strip mt-6 flex gap-2 overflow-x-auto pb-4">
      <button
        v-for="d in days"
        :key="d.toISOString()"
        type="button"
        class="flex min-w-[3.5rem] shrink-0 flex-col items-center rounded-xl border px-3 py-2"
        :class="
          isSameDay(d, selectedDate)
            ? 'border-primary bg-primary text-white'
            : 'border-line bg-white text-ink hover:border-primary'
        "
        @click="selectedDate = d"
      >
        <span class="text-[10px] font-semibold uppercase tracking-wide opacity-80">
          {{ d.toLocaleDateString(undefined, { weekday: 'short' }) }}
        </span>
        <span class="text-lg font-semibold">{{ d.getDate() }}</span>
      </button>
    </div>

    <h2 class="mt-6 font-display text-xl font-semibold text-ink">{{ dayHeading }}</h2>

    <div v-if="loading" class="py-16 text-center text-muted">Loading…</div>
    <div v-else-if="loadError" class="mt-4 rounded-xl bg-warn-bg p-4 text-sm text-warn">{{ loadError }}</div>

    <template v-else>
      <p v-if="cancelError" class="mt-4 rounded-xl bg-warn-bg p-3 text-sm text-warn">{{ cancelError }}</p>

      <div class="mt-4 divide-y divide-line rounded-2xl border border-line bg-surface">
        <div v-for="hour in hours" :key="hour" class="p-4">
          <div class="flex items-start justify-between gap-3">
            <span class="w-16 shrink-0 pt-1 text-sm font-medium text-muted">{{ formatHour(hour) }}</span>

            <div class="min-w-0 flex-1">
              <div v-if="rowInfo(hour).blocked" class="rounded-lg bg-line/60 px-3 py-1.5 text-sm text-muted">
                Blocked{{ rowInfo(hour).blocked!.note ? ' · ' + rowInfo(hour).blocked!.note : '' }}
              </div>
              <div v-else>
                <p v-if="rowInfo(hour).bookings.length" class="mb-1 text-xs text-muted">
                  {{ rowInfo(hour).bookings.length }} visiting
                </p>
                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="v in rowInfo(hour).bookings"
                    :key="v.id"
                    class="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary"
                  >
                    {{ v.user_name }}
                    <span v-if="v.note" class="font-normal text-primary/70">· {{ v.note }}</span>
                    <template v-if="v.can_edit">
                      <button
                        v-if="confirmingCancelId !== v.id"
                        type="button"
                        class="ml-0.5 text-primary/60 hover:text-warn"
                        title="Cancel this booking"
                        @click="confirmingCancelId = v.id"
                      >
                        ×
                      </button>
                      <span v-else class="ml-1 inline-flex items-center gap-1 text-xs font-normal text-warn">
                        Cancel?
                        <button
                          type="button"
                          class="font-semibold underline disabled:opacity-50"
                          :disabled="cancelling"
                          @click="handleCancel(v.id)"
                        >
                          Yes
                        </button>
                        <button type="button" class="underline" @click="confirmingCancelId = null">No</button>
                      </span>
                    </template>
                  </span>
                  <span v-if="!rowInfo(hour).bookings.length" class="text-sm text-muted">
                    {{ rowInfo(hour).isPast ? 'No one visited' : 'Open' }}
                  </span>
                </div>
              </div>
            </div>

            <button
              v-if="!rowInfo(hour).blocked && !rowInfo(hour).isPast && openHour !== hour"
              type="button"
              class="shrink-0 text-sm font-medium text-primary hover:underline"
              @click="openBookingForm(hour)"
            >
              {{ authStore.isFamily ? 'Add' : 'Book' }}
            </button>
          </div>

          <div v-if="openHour === hour" class="mt-3 rounded-xl border border-line bg-paper p-4">
            <div class="flex flex-wrap items-end gap-3">
              <div>
                <label :for="`duration-${hour}`" class="block text-xs font-semibold text-ink">Length</label>
                <select
                  :id="`duration-${hour}`"
                  v-model.number="bookingDurationMinutes"
                  class="mt-1 rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink"
                >
                  <option :value="30">30 min</option>
                  <option :value="60">1 hour</option>
                  <option :value="90">1.5 hours</option>
                  <option :value="120">2 hours</option>
                </select>
              </div>
              <div class="min-w-[10rem] flex-1">
                <label :for="`note-${hour}`" class="block text-xs font-semibold text-ink">Note (optional)</label>
                <input
                  :id="`note-${hour}`"
                  v-model="bookingNote"
                  type="text"
                  placeholder="e.g. Bringing the kids"
                  class="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink"
                />
              </div>
            </div>

            <label v-if="authStore.isFamily" class="mt-3 inline-flex items-center gap-2 text-sm text-muted">
              <input v-model="blockMode" type="checkbox" class="accent-primary" />
              Block this time instead (no visitors)
            </label>

            <p v-if="formError" class="mt-2 text-sm text-warn">{{ formError }}</p>

            <div class="mt-3 flex gap-2">
              <button
                type="button"
                :disabled="submitting"
                class="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-50"
                @click="submitBooking(hour)"
              >
                {{ submitting ? 'Saving…' : blockMode ? 'Block time' : 'Book this time' }}
              </button>
              <button type="button" class="rounded-xl px-4 py-2 text-sm text-muted" @click="closeBookingForm">
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* The date strip's native scrollbar otherwise renders at full OS thickness
   (e.g. 15-17px on Windows) right up against the date pills above it. Thin
   it out and give it its own row of space instead of overlapping them. */
.date-strip {
  scrollbar-width: thin;
  scrollbar-color: var(--color-line) transparent;
}

.date-strip::-webkit-scrollbar {
  height: 6px;
}

.date-strip::-webkit-scrollbar-track {
  background: transparent;
}

.date-strip::-webkit-scrollbar-thumb {
  background-color: var(--color-line);
  border-radius: 9999px;
}
</style>
