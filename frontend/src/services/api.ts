import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'
import router from '@/router'
import { clearStoredAuth, TOKEN_KEY } from '@/utils/authStorage'
import { API_BASE_URL, refreshAccessToken } from '@/services/session'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Endpoints where a 401 means "wrong credentials / bad link", not "session expired".
const AUTH_PATHS = ['/auth/login/', '/auth/join/', '/auth/refresh/']

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean }

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // Photo uploads send FormData. This instance defaults to a JSON
    // Content-Type; axios's own request pipeline only strips a FormData
    // body's Content-Type header down inside the browser adapter, by which
    // point it's too late — it JSON-stringifies the FormData earlier, in
    // its default transformRequest, whenever a JSON Content-Type is still
    // set at that point. Deleting it here, before that runs, is what keeps
    // the body a real FormData and lets the browser set its own boundary.
    // (Confirmed by exercising an actual upload — see PhotoUploadView tests.)
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    return config
  },
  (error) => Promise.reject(error)
)

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status
    const config = error.config as RetriableConfig | undefined
    const requestUrl = config?.url ?? ''
    const isAuthAttempt = AUTH_PATHS.some((path) => requestUrl.includes(path))

    if (status === 401 && config && !isAuthAttempt) {
      // The access token is short-lived. Try one silent refresh and replay the
      // request before treating the session as dead. Visitors join by link and
      // can't re-enter a password, so this is what keeps them signed in.
      if (!config._retried) {
        config._retried = true
        const token = await refreshAccessToken()
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
          return api(config)
        }
      }

      clearStoredAuth()
      if (router.currentRoute.value.name !== 'login') {
        router.push({
          name: 'login',
          query: { redirect: router.currentRoute.value.fullPath }
        })
      }
    }

    return Promise.reject(error)
  }
)

export default api
