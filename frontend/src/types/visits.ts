export type VisitKind = 'visit' | 'blocked'
export type VisitStatus = 'planned' | 'cancelled'

export interface Visit {
  id: number
  user_name: string
  start: string
  end: string
  note: string
  kind: VisitKind
  status: VisitStatus
  is_past: boolean
  can_edit: boolean
  created_at: string
}

export interface VisitWritePayload {
  start: string
  end: string
  note?: string
  kind?: VisitKind
}
