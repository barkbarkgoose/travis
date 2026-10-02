/** Pulls a user-facing message out of a DRF error response, if there is one. */
export function extractErrorMessage(err: unknown): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data
  if (typeof data?.detail === 'string') return data.detail
  if (data) {
    const firstKey = Object.keys(data)[0]
    const value = firstKey ? data[firstKey] : undefined
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
  }
  return ''
}
