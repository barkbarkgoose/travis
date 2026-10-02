/**
 * Client-side JWT inspection helpers.
 *
 * We decode the token payload without verifying its signature: the backend
 * remains the source of truth for validity. Reading the `exp` claim locally
 * lets the UI treat an expired token as logged out immediately instead of
 * firing requests that fail with 401.
 */

export interface JwtPayload {
  exp?: number
  [claim: string]: unknown
}

function base64UrlDecode(segment: string): string {
  const normalized = segment.replace(/-/g, '+').replace(/_/g, '/')
  const padding = normalized.length % 4 === 0 ? '' : '='.repeat(4 - (normalized.length % 4))
  const binary = atob(normalized + padding)
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

/** Decode the payload of a JWT, or return null if it is malformed. */
export function decodeJwtPayload(token: string): JwtPayload | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    return JSON.parse(base64UrlDecode(parts[1])) as JwtPayload
  } catch {
    return null
  }
}

/**
 * Return true when a token is missing, malformed, or past its `exp` claim.
 *
 * `leewaySeconds` treats tokens expiring within that window as already expired
 * so an in-flight request does not fail with a surprise 401.
 */
export function isTokenExpired(token: string | null | undefined, leewaySeconds = 5): boolean {
  if (!token) return true
  const payload = decodeJwtPayload(token)
  if (!payload) return true
  if (typeof payload.exp !== 'number') return false
  const now = Math.floor(Date.now() / 1000)
  return payload.exp <= now + leewaySeconds
}
