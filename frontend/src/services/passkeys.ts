/**
 * Passkey (WebAuthn) ceremonies against the backend.
 *
 * Each one is two calls: fetch options plus a signed `state`, let the browser
 * prompt for Face ID / fingerprint / PIN, then send the credential back with
 * the same `state`.
 */

import {
  browserSupportsWebAuthn,
  startAuthentication,
  startRegistration,
  WebAuthnError
} from '@simplewebauthn/browser'
import type {
  AuthenticationResponseJSON,
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON
} from '@simplewebauthn/browser'
import api from '@/services/api'
import type { LoginResponse, Passkey } from '@/types/auth'

interface Ceremony<T> {
  options: T
  state: string
}

export const passkeysSupported = browserSupportsWebAuthn

/** True when the person closed or cancelled the browser's passkey prompt. */
export function isPasskeyCancel(error: unknown): boolean {
  return (
    (error instanceof WebAuthnError && error.code === 'ERROR_CEREMONY_ABORTED') ||
    (error instanceof Error && error.name === 'NotAllowedError')
  )
}

/** Prompt for one of the user's passkeys and return proof to send to the backend. */
export async function provePasskey(): Promise<{
  state: string
  credential: AuthenticationResponseJSON
}> {
  const { data } = await api.post<Ceremony<PublicKeyCredentialRequestOptionsJSON>>(
    '/api/v1/auth/passkeys/auth/options/'
  )
  const credential = await startAuthentication({ optionsJSON: data.options })
  return { state: data.state, credential }
}

export async function signInWithPasskey(): Promise<LoginResponse> {
  const proof = await provePasskey()
  const { data } = await api.post<LoginResponse>('/api/v1/auth/passkeys/login/', proof)
  return data
}

export async function createPasskey(
  name = ''
): Promise<LoginResponse & { passkey: Passkey }> {
  const { data: ceremony } = await api.post<Ceremony<PublicKeyCredentialCreationOptionsJSON>>(
    '/api/v1/auth/passkeys/register/options/'
  )
  const credential = await startRegistration({ optionsJSON: ceremony.options })
  const { data } = await api.post<LoginResponse & { passkey: Passkey }>(
    '/api/v1/auth/passkeys/',
    { state: ceremony.state, credential, name }
  )
  return data
}

export async function listPasskeys(): Promise<Passkey[]> {
  const { data } = await api.get<Passkey[]>('/api/v1/auth/passkeys/')
  return data
}

export async function deletePasskey(id: number): Promise<void> {
  await api.delete(`/api/v1/auth/passkeys/${id}/`)
}

export async function changePassword(newPassword: string): Promise<void> {
  const proof = await provePasskey()
  await api.post('/api/v1/auth/password/', { ...proof, new_password: newPassword })
}

/** Open a Django admin session (staff, passkey session only), then go there. */
export async function openAdmin(): Promise<void> {
  await api.post('/api/v1/auth/admin-session/')
  window.location.assign('/admin/')
}
