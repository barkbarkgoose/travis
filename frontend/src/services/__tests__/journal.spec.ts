import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPatch, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn()
}))
vi.mock('@/services/api', () => ({
  default: { get: apiGet, post: apiPost, patch: apiPatch, delete: apiDelete }
}))

import * as journalApi from '@/services/journal'

describe('journal service', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    apiPatch.mockReset()
    apiDelete.mockReset()
  })

  it('createDraftEntry posts to the entries endpoint', async () => {
    apiPost.mockResolvedValue({ data: { id: 1 } })
    const entry = await journalApi.createDraftEntry({ pain_level: 3 })
    expect(apiPost).toHaveBeenCalledWith('/api/v1/journal/entries/', { pain_level: 3 })
    expect(entry).toEqual({ id: 1 })
  })

  it('updateEntry patches the specific entry', async () => {
    apiPatch.mockResolvedValue({ data: { id: 5 } })
    await journalApi.updateEntry(5, { pain_level: 4 })
    expect(apiPatch).toHaveBeenCalledWith('/api/v1/journal/entries/5/', { pain_level: 4 })
  })

  it('deleteEntry deletes the specific entry', async () => {
    apiDelete.mockResolvedValue({ data: undefined })
    await journalApi.deleteEntry(5)
    expect(apiDelete).toHaveBeenCalledWith('/api/v1/journal/entries/5/')
  })

  it('submitEntry posts with no body', async () => {
    apiPost.mockResolvedValue({ data: { id: 5, status: 'submitted' } })
    await journalApi.submitEntry(5)
    expect(apiPost).toHaveBeenCalledWith('/api/v1/journal/entries/5/submit/')
  })

  it('listEntries omits the all param by default', async () => {
    apiGet.mockResolvedValue({ data: { results: [] } })
    await journalApi.listEntries()
    expect(apiGet).toHaveBeenCalledWith('/api/v1/journal/entries/', { params: undefined })
  })

  it('listEntries passes all=1 when requested', async () => {
    apiGet.mockResolvedValue({ data: { results: [] } })
    await journalApi.listEntries({ all: true })
    expect(apiGet).toHaveBeenCalledWith('/api/v1/journal/entries/', { params: { all: 1 } })
  })

  it('addAddendum posts the body text', async () => {
    apiPost.mockResolvedValue({ data: { id: 9 } })
    await journalApi.addAddendum(5, 'Correction: right knee.')
    expect(apiPost).toHaveBeenCalledWith('/api/v1/journal/entries/5/addenda/', {
      body: 'Correction: right knee.'
    })
  })

  it('uploadPhoto builds multipart form data with the optional fields', async () => {
    apiPost.mockResolvedValue({ data: { id: 1 } })
    const file = new File(['bytes'], 'photo.jpg', { type: 'image/jpeg' })
    Object.defineProperty(file, 'lastModified', { value: 1700000000000 })

    await journalApi.uploadPhoto(5, file, { bodyArea: 'bruising', caption: 'Left arm' })

    expect(apiPost).toHaveBeenCalledTimes(1)
    const [url, form] = apiPost.mock.calls[0]
    expect(url).toBe('/api/v1/journal/entries/5/photos/')
    expect(form).toBeInstanceOf(FormData)
    expect(form.get('file')).toBe(file)
    expect(form.get('body_area')).toBe('bruising')
    expect(form.get('caption')).toBe('Left arm')
    expect(form.get('client_last_modified')).toBe('1700000000000')
  })

  it('uploadPhoto omits optional fields when not given', async () => {
    apiPost.mockResolvedValue({ data: { id: 1 } })
    const file = new File(['bytes'], 'photo.jpg', { type: 'image/jpeg' })
    Object.defineProperty(file, 'lastModified', { value: 0 })

    await journalApi.uploadPhoto(5, file)

    const form = apiPost.mock.calls[0][1] as FormData
    expect(form.get('body_area')).toBeNull()
    expect(form.get('caption')).toBeNull()
    expect(form.get('client_last_modified')).toBeNull()
  })
})
