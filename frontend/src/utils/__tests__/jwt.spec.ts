import { describe, expect, it } from 'vitest'
import { decodeJwtPayload, isTokenExpired } from '@/utils/jwt'

function makeToken(payload: Record<string, unknown>): string {
  const encode = (value: Record<string, unknown>) =>
    btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.signature`
}

describe('jwt utils', () => {
  it('decodes the payload', () => {
    const token = makeToken({ sub: 'user-1' })
    expect(decodeJwtPayload(token)?.sub).toBe('user-1')
  })

  it('treats a missing token as expired', () => {
    expect(isTokenExpired(null)).toBe(true)
    expect(isTokenExpired(undefined)).toBe(true)
  })

  it('treats a malformed token as expired', () => {
    expect(isTokenExpired('not-a-jwt')).toBe(true)
  })

  it('returns false for a future exp', () => {
    const token = makeToken({ exp: Math.floor(Date.now() / 1000) + 3600 })
    expect(isTokenExpired(token)).toBe(false)
  })

  it('returns true for a past exp', () => {
    const token = makeToken({ exp: Math.floor(Date.now() / 1000) - 3600 })
    expect(isTokenExpired(token)).toBe(true)
  })

  it('treats a token expiring within the leeway as expired', () => {
    const token = makeToken({ exp: Math.floor(Date.now() / 1000) + 2 })
    expect(isTokenExpired(token, 5)).toBe(true)
  })

  it('returns false when the token has no exp claim', () => {
    const token = makeToken({ sub: 'user-1' })
    expect(isTokenExpired(token)).toBe(false)
  })
})
