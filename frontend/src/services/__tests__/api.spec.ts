import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios'

const { push, refreshAccessToken } = vi.hoisted(() => ({ push: vi.fn(), refreshAccessToken: vi.fn() }))
vi.mock('@/router', () => ({
  default: { push, currentRoute: { value: { name: 'dashboard', fullPath: '/dashboard' } } }
}))
vi.mock('@/services/session', () => ({ API_BASE_URL: 'http://api.test', refreshAccessToken }))

import api from '@/services/api'
import { REFRESH_KEY, TOKEN_KEY } from '@/utils/authStorage'

/** Adapter that answers 401 unless the bearer token is `good`. */
function fakeServer(seen: string[]): AxiosAdapter {
  return async (config: InternalAxiosRequestConfig) => {
    const auth = String(config.headers.Authorization ?? '')
    seen.push(`${config.url} ${auth}`)
    if (auth === 'Bearer good') {
      return { data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config }
    }
    const error = Object.assign(new Error('401'), {
      isAxiosError: true,
      config,
      response: { status: 401, data: {}, statusText: 'Unauthorized', headers: {}, config }
    })
    throw error
  }
}

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear()
    push.mockReset()
    refreshAccessToken.mockReset()
  })

  it('refreshes once on 401 and replays the request with the new token', async () => {
    const seen: string[] = []
    api.defaults.adapter = fakeServer(seen)
    localStorage.setItem(TOKEN_KEY, 'expired')
    // The real refreshAccessToken persists the new token before resolving, and the
    // request interceptor re-reads storage when the request is replayed.
    refreshAccessToken.mockImplementation(async () => {
      localStorage.setItem(TOKEN_KEY, 'good')
      return 'good'
    })

    const response = await api.get('/api/v1/things/')

    expect(response.data).toEqual({ ok: true })
    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
    expect(seen).toEqual(['/api/v1/things/ Bearer expired', '/api/v1/things/ Bearer good'])
    expect(push).not.toHaveBeenCalled()
  })

  it('clears the session and goes to login when the refresh fails', async () => {
    api.defaults.adapter = fakeServer([])
    localStorage.setItem(TOKEN_KEY, 'expired')
    localStorage.setItem(REFRESH_KEY, 'dead')
    refreshAccessToken.mockResolvedValue(null)

    await expect(api.get('/api/v1/things/')).rejects.toBeTruthy()

    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull()
    expect(push).toHaveBeenCalledWith({ name: 'login', query: { redirect: '/dashboard' } })
  })

  it('does not try to refresh when a join attempt is rejected', async () => {
    api.defaults.adapter = fakeServer([])

    await expect(api.post('/api/v1/auth/join/', {})).rejects.toBeTruthy()

    expect(refreshAccessToken).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('only retries a request once', async () => {
    api.defaults.adapter = fakeServer([])
    refreshAccessToken.mockResolvedValue('still-bad')

    await expect(api.get('/api/v1/things/')).rejects.toBeTruthy()

    expect(refreshAccessToken).toHaveBeenCalledTimes(1)
  })

  // Regression test: a real browser upload once failed because this instance's
  // default JSON Content-Type survived into axios's transformRequest step,
  // which JSON-stringifies a FormData body whenever a JSON content type is
  // still set — silently destroying the upload before it reached the network.
  // Confirmed against the real request interceptor rather than a fake adapter,
  // since a fake adapter bypasses the exact pipeline stage that broke.
  it('strips the default Content-Type header for a FormData body, before axios can stringify it', () => {
    const requestInterceptor = (api.interceptors.request as unknown as {
      handlers: { fulfilled: (config: InternalAxiosRequestConfig) => InternalAxiosRequestConfig }[]
    }).handlers[0].fulfilled

    const form = new FormData()
    form.append('file', new File(['x'], 'x.jpg'))
    const config = {
      headers: { 'Content-Type': 'application/json' },
      data: form
    } as unknown as InternalAxiosRequestConfig

    const result = requestInterceptor(config)

    expect('Content-Type' in result.headers).toBe(false)
  })

  it('leaves the Content-Type header alone for a plain JSON body', () => {
    const requestInterceptor = (api.interceptors.request as unknown as {
      handlers: { fulfilled: (config: InternalAxiosRequestConfig) => InternalAxiosRequestConfig }[]
    }).handlers[0].fulfilled

    const config = {
      headers: { 'Content-Type': 'application/json' },
      data: { pain_level: 3 }
    } as unknown as InternalAxiosRequestConfig

    const result = requestInterceptor(config)

    expect(result.headers['Content-Type']).toBe('application/json')
  })
})
