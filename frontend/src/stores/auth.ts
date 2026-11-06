import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  User,
  LoginCredentials,
  JoinRequest,
  JoinResponse,
  LoginResponse,
  UserSettings,
  UserSettingsUpdate
} from '@/types/auth'
import { isTokenExpired } from '@/utils/jwt'
import {
  REFRESH_KEY,
  SETTINGS_KEY,
  TOKEN_KEY,
  USER_KEY,
  clearStoredAuth
} from '@/utils/authStorage'
import api from '@/services/api'
import { refreshAccessToken } from '@/services/session'
import { createPasskey, signInWithPasskey } from '@/services/passkeys'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<User | null>(null)
  const userSettings = ref<UserSettings | null>(null)

  const isAuthenticated = computed(() => !!token.value && !isTokenExpired(token.value))
  // Family powers need a passkey session; the backend enforces the same rule.
  const isFamily = computed(() => user.value?.role === 'family' && !user.value?.needs_passkey)
  /** Something on the account page has to be done before the rest of the app. */
  const needsAccountSetup = computed(
    () => !!user.value && (!!user.value.needs_passkey || user.value.has_password === false)
  )

  function clearAuthState(): void {
    token.value = null
    user.value = null
    userSettings.value = null
    clearStoredAuth()
  }

  function hasUsableRefreshToken(): boolean {
    return !isTokenExpired(localStorage.getItem(REFRESH_KEY))
  }

  function loadFromStorage(): void {
    const storedToken = localStorage.getItem(TOKEN_KEY)

    // A missing or expired/malformed access token means logged out for now. The
    // stored session is only wiped when there is no usable refresh token left:
    // otherwise restoreSession() can silently renew it.
    if (!storedToken || isTokenExpired(storedToken)) {
      if (hasUsableRefreshToken()) {
        token.value = null
        user.value = null
        userSettings.value = null
      } else {
        clearAuthState()
      }
      return
    }

    const storedUser = localStorage.getItem(USER_KEY)
    const storedSettings = localStorage.getItem(SETTINGS_KEY)

    token.value = storedToken
    if (storedUser) {
      user.value = JSON.parse(storedUser)
    }
    if (storedSettings) {
      userSettings.value = JSON.parse(storedSettings)
    }
  }

  function storeUser(nextUser: User): void {
    user.value = nextUser
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
    if (nextUser.settings) {
      userSettings.value = nextUser.settings
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(nextUser.settings))
    }
  }

  async function fetchUserSettings(): Promise<UserSettings | null> {
    if (!token.value) return null
    try {
      const response = await api.get<UserSettings>('/api/v1/auth/settings/')
      userSettings.value = response.data
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(response.data))
      if (user.value) {
        user.value.settings = response.data
        localStorage.setItem(USER_KEY, JSON.stringify(user.value))
      }
      return response.data
    } catch {
      return null
    }
  }

  async function updateUserSettings(settings: UserSettingsUpdate): Promise<UserSettings> {
    const response = await api.patch<UserSettings>('/api/v1/auth/settings/', settings)
    userSettings.value = response.data
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(response.data))
    if (user.value) {
      user.value.settings = response.data
      localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    }
    return response.data
  }

  async function saveApiKey(provider: string, apiKey: string): Promise<boolean> {
    if (!token.value || !provider) return false
    try {
      await updateUserSettings({ api_keys: { [provider]: apiKey.trim() } })
      return true
    } catch {
      return false
    }
  }

  function startSession(data: LoginResponse): void {
    token.value = data.access
    localStorage.setItem(TOKEN_KEY, data.access)
    if (data.refresh) {
      localStorage.setItem(REFRESH_KEY, data.refresh)
    }
    if (data.user) {
      storeUser(data.user)
    }
  }

  async function login(credentials: LoginCredentials): Promise<void> {
    const response = await api.post<LoginResponse>('/api/v1/auth/login/', credentials)
    startSession(response.data)
  }

  async function loginWithPasskey(): Promise<void> {
    startSession(await signInWithPasskey())
  }

  /** Save a new passkey. The backend answers with a fresh passkey session. */
  async function addPasskey(name = ''): Promise<void> {
    startSession(await createPasskey(name))
  }

  /** Sign up through a shared invite link: the only way to create an account. */
  async function join(payload: JoinRequest): Promise<void> {
    const response = await api.post<JoinResponse>('/api/v1/auth/join/', payload)
    startSession(response.data)
  }

  /** Give an email and password to a visitor who joined before passwords existed. */
  async function claimAccount(email: string, password: string): Promise<void> {
    const response = await api.post<User>('/api/v1/auth/account/', { email, password })
    storeUser({ ...user.value, ...response.data })
  }

  /**
   * Restore a session from storage, silently renewing an expired access token
   * with the refresh token. Called by the router guard before every navigation.
   */
  async function restoreSession(): Promise<void> {
    const storedToken = localStorage.getItem(TOKEN_KEY)
    if ((!storedToken || isTokenExpired(storedToken)) && hasUsableRefreshToken()) {
      const renewed = await refreshAccessToken()
      if (!renewed) {
        clearAuthState()
        return
      }
    }
    loadFromStorage()
  }

  function logout(): void {
    clearAuthState()
  }

  return {
    token,
    user,
    userSettings,
    isAuthenticated,
    isFamily,
    needsAccountSetup,
    storeUser,
    loadFromStorage,
    restoreSession,
    fetchUserSettings,
    updateUserSettings,
    saveApiKey,
    login,
    loginWithPasskey,
    addPasskey,
    join,
    claimAccount,
    logout
  }
})
