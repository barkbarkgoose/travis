export interface LoginRequest {
  email: string
  password: string
}

export type Role = 'visitor' | 'family'

export interface JoinRequest {
  token: string
  full_name: string
  email: string
  password: string
}

export interface LoginResponse {
  access: string
  refresh: string
  user?: User
}

export type JoinResponse = LoginResponse

export interface ApiKeyStatus {
  is_configured: boolean
  preview: string
}

export interface UserSettings {
  theme_colors?: Record<string, string>
  default_view?: string
  default_ai_provider?: string
  api_keys_status?: Record<string, ApiKeyStatus>
}

export interface UserSettingsUpdate {
  theme_colors?: Record<string, string>
  default_view?: string
  default_ai_provider?: string
  api_keys?: Record<string, string>
}

export interface User {
  id: number
  email: string
  name: string
  role: Role
  organization?: {
    id: number
    name: string
  }
  settings?: UserSettings
  /** False for visitors who joined before accounts had passwords. */
  has_password?: boolean
  passkey_count?: number
  /** Family account whose session wasn't opened with a passkey: family powers are off. */
  needs_passkey?: boolean
}

export interface Passkey {
  id: number
  name: string
  created_at: string
  last_used_at: string | null
}

export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
}

export interface LoginCredentials {
  email: string
  password: string
}
