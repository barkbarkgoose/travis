/**
 * Copy and options for the visit questionnaire, built from the guidance in
 * `daily-journaling.md` and `docs/SECURITY_AND_LEGAL.md`. Keep the answer keys
 * here in sync with `ANSWER_FIELD_MAX_LENGTHS` in
 * `backend/apps/journal/serializers.py` — the server drops anything it
 * doesn't recognize.
 *
 * Kept to 3 steps deliberately: fewer, more natural free-text prompts read as
 * more credible than many short fragmented ones (see docs/SECURITY_AND_LEGAL.md).
 */

import type { PainSource, Trend } from '@/types/journal'

export interface SelectOption<T extends string> {
  value: T
  label: string
}

export const TREND_OPTIONS: SelectOption<Trend>[] = [
  { value: 'better', label: 'Better than last time' },
  { value: 'same', label: 'About the same' },
  { value: 'worse', label: 'Worse than last time' },
  { value: 'unsure', label: 'Not sure / first visit' }
]

export const PAIN_SOURCE_OPTIONS: SelectOption<PainSource>[] = [
  { value: 'travis_said', label: 'Travis said' },
  { value: 'observed', label: 'I observed it' }
]

export interface QuestionnaireStep {
  id: string
  title: string
  guidance?: string
}

export const QUESTIONNAIRE_STEPS: QuestionnaireStep[] = [
  {
    id: 'visit',
    title: 'This visit',
    guidance: 'Just the basics — you can fill in the rest as you go.'
  },
  {
    id: 'overall',
    title: 'Overall & pain',
    guidance:
      'Write what you saw. If Travis told you his pain level, note that it’s what he said, not what you observed.'
  },
  {
    id: 'photos',
    title: 'Photos & notes',
    guidance:
      'Take a couple of consistent photos each visit — similar distance and lighting makes day-to-day comparison easier.'
  }
]

export const PHOTO_NOTES_GUIDANCE = 'What do the photos show? A sentence or two is plenty.'

export const ADDITIONAL_NOTES_LABEL = 'Anything else?'
export const ADDITIONAL_NOTES_GUIDANCE =
  'Surgeries or procedures, MRI/imaging results, treatments you saw done, anything you heard ' +
  'secondhand (say who told you), and any difficulties — moving, eating, sleeping, breathing, ' +
  'self-care. Medical details are what you were told, not the official record, so don’t worry ' +
  'about getting the clinical terms exactly right. Don’t guess at fault, and leave out insurance ' +
  'numbers, SSNs, or birthdates.'
