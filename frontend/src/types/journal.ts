export type BodyArea =
  | 'bruising'
  | 'road_rash'
  | 'knee_brace'
  | 'shoulder'
  | 'ribs'
  | 'other'
  | 'general'

export type PainSource = 'travis_said' | 'observed'
export type Trend = 'better' | 'same' | 'worse' | 'unsure'
export type EntryStatus = 'draft' | 'submitted'

// Mirrors ANSWER_FIELD_MAX_LENGTHS in backend/apps/journal/serializers.py —
// keep the two in sync when a question is added, renamed, or removed.
export interface EntryAnswers {
  who_else_was_there?: string
  overall_note?: string
  alertness_mood?: string
  /** What the photos in this entry show — required before submitting. */
  photo_notes?: string
  /** Catch-all: surgeries, treatments, difficulties, anything else. */
  additional_notes?: string
}

export interface Addendum {
  id: number
  author_name: string
  body: string
  created_at: string
}

export interface PhotoUrls {
  original: string
  display: string
  thumb: string
}

export interface Photo {
  id: number
  uploader_name: string
  uploaded_at: string
  exif_taken_at: string | null
  body_area: BodyArea
  caption: string
  urls: PhotoUrls
}

export interface Entry {
  id: number
  author_name: string
  occurred_at: string
  created_at: string
  updated_at: string
  submitted_at: string | null
  is_locked: boolean
  can_edit: boolean
  edit_window_ends_at: string | null
  pain_level: number | null
  pain_source: PainSource | ''
  trend: Trend | ''
  answers: EntryAnswers
  questionnaire_version: number
  status: EntryStatus
  photos: Photo[]
  addenda: Addendum[]
}

export interface EntryWritePayload {
  occurred_at?: string
  pain_level?: number | null
  pain_source?: PainSource | ''
  trend?: Trend | ''
  answers?: EntryAnswers
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
