/**
 * Local storage keys and helpers for the auth session.
 *
 * Kept separate from the Pinia store so the Axios interceptor can clear a dead
 * session without importing the store (which would create a circular import).
 * The store re-reads storage on the next navigation, so clearing here is enough
 * to make `isAuthenticated` false.
 */

export const TOKEN_KEY = 'auth_token'
export const REFRESH_KEY = 'refresh_token'
export const USER_KEY = 'auth_user'
export const SETTINGS_KEY = 'auth_user_settings'

export function clearStoredAuth(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem(SETTINGS_KEY)
}
