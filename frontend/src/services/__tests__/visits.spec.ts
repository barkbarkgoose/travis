import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, apiPost, apiPatch } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn()
}))
vi.mock('@/services/api', () => ({ default: { get: apiGet, post: apiPost, patch: apiPatch } }))

import * as visitsApi from '@/services/visits'

describe('visits service', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    apiPatch.mockReset()
  })

  it('listVisits passes the from/to window as ISO strings', async () => {
    apiGet.mockResolvedValue({ data: { results: [] } })
    const from = new Date('2026-09-27T00:00:00.000Z')
    const to = new Date('2026-09-28T00:00:00.000Z')
    await visitsApi.listVisits(from, to)
    expect(apiGet).toHaveBeenCalledWith('/api/v1/visits/', {
      params: { from: from.toISOString(), to: to.toISOString() }
    })
  })

  it('createVisit posts the payload', async () => {
    apiPost.mockResolvedValue({ data: { id: 1 } })
    const payload = { start: '2026-09-27T10:00:00.000Z', end: '2026-09-27T11:00:00.000Z', note: 'Hi' }
    const visit = await visitsApi.createVisit(payload)
    expect(apiPost).toHaveBeenCalledWith('/api/v1/visits/', payload)
    expect(visit).toEqual({ id: 1 })
  })

  it('updateVisit patches the specific visit', async () => {
    apiPatch.mockResolvedValue({ data: { id: 3 } })
    await visitsApi.updateVisit(3, { note: 'Rescheduled' })
    expect(apiPatch).toHaveBeenCalledWith('/api/v1/visits/3/', { note: 'Rescheduled' })
  })

  it('cancelVisit posts to the cancel endpoint with no body', async () => {
    apiPost.mockResolvedValue({ data: { id: 3, status: 'cancelled' } })
    await visitsApi.cancelVisit(3)
    expect(apiPost).toHaveBeenCalledWith('/api/v1/visits/3/cancel/')
  })
})
