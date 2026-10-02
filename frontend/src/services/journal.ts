import api from '@/services/api'
import type { Addendum, Entry, EntryWritePayload, Paginated, Photo } from '@/types/journal'

export async function createDraftEntry(payload: EntryWritePayload = {}): Promise<Entry> {
  const { data } = await api.post<Entry>('/api/v1/journal/entries/', payload)
  return data
}

export async function updateEntry(id: number, payload: EntryWritePayload): Promise<Entry> {
  const { data } = await api.patch<Entry>(`/api/v1/journal/entries/${id}/`, payload)
  return data
}

export async function fetchEntry(id: number): Promise<Entry> {
  const { data } = await api.get<Entry>(`/api/v1/journal/entries/${id}/`)
  return data
}

/** Only works while the entry is still a draft — the server rejects a submitted one. */
export async function deleteEntry(id: number): Promise<void> {
  await api.delete(`/api/v1/journal/entries/${id}/`)
}

export async function submitEntry(id: number): Promise<Entry> {
  const { data } = await api.post<Entry>(`/api/v1/journal/entries/${id}/submit/`)
  return data
}

/** The caller's own entries. Family accounts pass `all: true` to see everyone's. */
export async function listEntries(options: { all?: boolean } = {}): Promise<Entry[]> {
  const { data } = await api.get<Paginated<Entry>>('/api/v1/journal/entries/', {
    params: options.all ? { all: 1 } : undefined
  })
  return data.results
}

export async function addAddendum(entryId: number, body: string): Promise<Addendum> {
  const { data } = await api.post<Addendum>(`/api/v1/journal/entries/${entryId}/addenda/`, {
    body
  })
  return data
}

export async function uploadPhoto(
  entryId: number,
  file: File,
  options: { bodyArea?: string; caption?: string } = {}
): Promise<Photo> {
  const form = new FormData()
  form.append('file', file)
  if (options.bodyArea) form.append('body_area', options.bodyArea)
  if (options.caption) form.append('caption', options.caption)
  if (file.lastModified) form.append('client_last_modified', String(file.lastModified))

  const { data } = await api.post<Photo>(`/api/v1/journal/entries/${entryId}/photos/`, form)
  return data
}
