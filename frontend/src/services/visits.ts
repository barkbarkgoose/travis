import api from '@/services/api'
import type { Paginated } from '@/types/journal'
import type { Visit, VisitWritePayload } from '@/types/visits'

/** All bookings and blocks whose time overlaps [from, to). */
export async function listVisits(from: Date, to: Date): Promise<Visit[]> {
  const { data } = await api.get<Paginated<Visit>>('/api/v1/visits/', {
    params: { from: from.toISOString(), to: to.toISOString() }
  })
  return data.results
}

export async function createVisit(payload: VisitWritePayload): Promise<Visit> {
  const { data } = await api.post<Visit>('/api/v1/visits/', payload)
  return data
}

export async function updateVisit(id: number, payload: Partial<VisitWritePayload>): Promise<Visit> {
  const { data } = await api.patch<Visit>(`/api/v1/visits/${id}/`, payload)
  return data
}

export async function cancelVisit(id: number): Promise<Visit> {
  const { data } = await api.post<Visit>(`/api/v1/visits/${id}/cancel/`)
  return data
}
