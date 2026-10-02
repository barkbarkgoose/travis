import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { apiPost, refreshAccessToken } = vi.hoisted(() => ({
  apiPost: vi.fn(),
  refreshAccessToken: vi.fn()
}))
vi.mock('@/services/api', () => ({ default: { post: apiPost, get: vi.fn(), patch: vi.fn() } }))
vi.mock('@/services/session', () => ({ refreshAccessToken }))

import { useAuthStore } from '@/stores/auth'
import { REFRESH_KEY, TOKEN_KEY, USER_KEY } from '@/utils/authStorage'

function makeToken(expOffsetSeconds: number): string {
  const encode = (value: Record<string, unknown>) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  const exp = Math.floor(Date.now() / 1000) + expOffsetSeconds
  return `${encode({ alg: 'HS256' })}.${encode({ exp })}.sig`
}

const visitor = { id: 7, email: 'v@visitors.invalid', name: 'Maria Lopez', role: 'visitor' as const }

describe('auth store', () => {
  beforeEach(() => {
    localStorage.clear()
    apiPost.mockReset()
    refreshAccessToken.mockReset()
    setActivePinia(createPinia())
  })

  it('join stores both tokens and the visitor', async () => {
    apiPost.mockResolvedValue({ data: { access: makeToken(3600), refresh: makeToken(86400), user: visitor } })
    const store = useAuthStore()

    await store.join({ token: 'abc', full_name: 'Maria Lopez' })

    expect(apiPost).toHaveBeenCalledWith('/api/v1/auth/join/', { token: 'abc', full_name: 'Maria Lopez' })
    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.name).toBe('Maria Lopez')
    expect(store.isFamily).toBe(false)
    expect(localStorage.getItem(REFRESH_KEY)).not.toBeNull()
  })

  it('isFamily is true for family accounts', async () => {
    apiPost.mockResolvedValue({
      data: { access: makeToken(3600), refresh: makeToken(86400), user: { ...visitor, role: 'family' } }
    })
    const store = useAuthStore()
    await store.login({ email: 'a@b.c', password: 'pw' })
    expect(store.isFamily).toBe(true)
  })

  it('loadFromStorage keeps the refresh token when only the access token expired', () => {
    localStorage.setItem(TOKEN_KEY, makeToken(-60))
    localStorage.setItem(REFRESH_KEY, makeToken(86400))
    const store = useAuthStore()

    store.loadFromStorage()

    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem(REFRESH_KEY)).not.toBeNull()
  })

  it('loadFromStorage wipes everything when both tokens are dead', () => {
    localStorage.setItem(TOKEN_KEY, makeToken(-60))
    localStorage.setItem(REFRESH_KEY, makeToken(-60))
    localStorage.setItem(USER_KEY, JSON.stringify(visitor))
    const store = useAuthStore()

    store.loadFromStorage()

    expect(localStorage.getItem(REFRESH_KEY)).toBeNull()
    expect(localStorage.getItem(USER_KEY)).toBeNull()
  })

  it('restoreSession silently renews an expired access token', async () => {
    localStorage.setItem(TOKEN_KEY, makeToken(-60))
    localStorage.setItem(REFRESH_KEY, makeToken(86400))
    localStorage.setItem(USER_KEY, JSON.stringify(visitor))
    refreshAccessToken.mockImplementation(async () => {
      localStorage.setItem(TOKEN_KEY, makeToken(3600))
      return 'renewed'
    })
    const store = useAuthStore()

    await store.restoreSession()

    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.name).toBe('Maria Lopez')
  })

  it('restoreSession logs out when the refresh is rejected', async () => {
    localStorage.setItem(TOKEN_KEY, makeToken(-60))
    localStorage.setItem(REFRESH_KEY, makeToken(86400))
    refreshAccessToken.mockResolvedValue(null)
    const store = useAuthStore()

    await store.restoreSession()

    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull()
  })

  it('restoreSession does not call refresh when the access token is still valid', async () => {
    localStorage.setItem(TOKEN_KEY, makeToken(3600))
    localStorage.setItem(REFRESH_KEY, makeToken(86400))
    const store = useAuthStore()

    await store.restoreSession()

    expect(refreshAccessToken).not.toHaveBeenCalled()
    expect(store.isAuthenticated).toBe(true)
  })
})
