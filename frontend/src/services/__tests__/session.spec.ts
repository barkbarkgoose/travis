import { beforeEach, describe, expect, it, vi } from 'vitest'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('axios', () => ({ default: { create: () => ({ post }) } }))

import { refreshAccessToken } from '@/services/session'
import { REFRESH_KEY, TOKEN_KEY } from '@/utils/authStorage'

describe('refreshAccessToken', () => {
  beforeEach(() => {
    localStorage.clear()
    post.mockReset()
  })

  it('returns null without calling the API when there is no refresh token', async () => {
    expect(await refreshAccessToken()).toBeNull()
    expect(post).not.toHaveBeenCalled()
  })

  it('stores the new access and rotated refresh tokens', async () => {
    localStorage.setItem(REFRESH_KEY, 'old-refresh')
    post.mockResolvedValue({ data: { access: 'new-access', refresh: 'new-refresh' } })

    expect(await refreshAccessToken()).toBe('new-access')
    expect(post).toHaveBeenCalledWith('/api/v1/auth/refresh/', { refresh: 'old-refresh' })
    expect(localStorage.getItem(TOKEN_KEY)).toBe('new-access')
    expect(localStorage.getItem(REFRESH_KEY)).toBe('new-refresh')
  })

  it('shares one request between concurrent callers', async () => {
    localStorage.setItem(REFRESH_KEY, 'old-refresh')
    post.mockResolvedValue({ data: { access: 'a', refresh: 'r' } })

    const results = await Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken()
    ])
    expect(results).toEqual(['a', 'a', 'a'])
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('returns null and keeps the old tokens when the refresh is rejected', async () => {
    localStorage.setItem(REFRESH_KEY, 'old-refresh')
    localStorage.setItem(TOKEN_KEY, 'old-access')
    post.mockRejectedValue(new Error('401'))

    expect(await refreshAccessToken()).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBe('old-access')
  })

  it('allows a new refresh after the previous one settled', async () => {
    localStorage.setItem(REFRESH_KEY, 'r1')
    post.mockResolvedValue({ data: { access: 'a1', refresh: 'r2' } })
    await refreshAccessToken()
    post.mockResolvedValue({ data: { access: 'a2', refresh: 'r3' } })
    expect(await refreshAccessToken()).toBe('a2')
    expect(post).toHaveBeenCalledTimes(2)
  })
})
