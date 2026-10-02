/**
 * Silent access-token refresh.
 *
 * Uses a bare Axios client (no interceptors) so a failing refresh can never
 * trigger another refresh, and lives apart from `api.ts` so the auth store can
 * use it without importing the router.
 *
 * Concurrent callers share one in-flight request. The backend rotates the
 * refresh token on every use, so two parallel refreshes would race and the
 * loser would be left holding a stale token.
 */

import axios from 'axios'
import { REFRESH_KEY, TOKEN_KEY } from '@/utils/authStorage'

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8800'

const bare = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' }
})

let inFlight: Promise<string | null> | null = null

async function requestRefresh(): Promise<string | null> {
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh) return null
  try {
    const { data } = await bare.post<{ access: string; refresh?: string }>(
      '/api/v1/auth/refresh/',
      { refresh }
    )
    localStorage.setItem(TOKEN_KEY, data.access)
    if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh)
    return data.access
  } catch {
    return null
  }
}

/** Exchange the stored refresh token for a new access token, or null if that fails. */
export function refreshAccessToken(): Promise<string | null> {
  if (!inFlight) {
    inFlight = requestRefresh().finally(() => {
      inFlight = null
    })
  }
  return inFlight
}
