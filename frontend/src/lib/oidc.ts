/**
 * Browser side of the enterprise SSO: Authorization Code + PKCE.
 *
 * The backend already does the hard part — `/api/auth/oidc/session`
 * verifies the id_token's signature against the provider's JWKS, its
 * issuer and audience, and turns the claims into an Ermes session cookie.
 * Until 18 September 2026 nothing on this side produced a token: the
 * "Accedi con SSO" button showed a notification and stopped.
 *
 * The flow is the one every SPA uses (Entra ID "single-page application",
 * Keycloak "public client"): no client secret in the browser, the code is
 * bound to a PKCE verifier, `state` guards the redirect, and `nonce` is
 * checked in the id_token before it is handed to the backend. Discovery
 * comes from `{issuer}/.well-known/openid-configuration`, so only issuer
 * and client_id need configuring.
 */

export type OidcConfig = { enabled: boolean; client_id?: string; issuer?: string }

type Discovery = { authorization_endpoint: string; token_endpoint: string }

const STORAGE_KEY = 'ermes_oidc_login'
const SCOPE = 'openid profile email'

function base64url(bytes: Uint8Array): string {
  let text = ''
  for (const b of bytes) text += String.fromCharCode(b)
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function randomString(bytes = 32): string {
  const buffer = new Uint8Array(bytes)
  crypto.getRandomValues(buffer)
  return base64url(buffer)
}

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return base64url(new Uint8Array(digest))
}

export function redirectUri(): string {
  return window.location.origin + '/'
}

async function discover(issuer: string): Promise<Discovery> {
  const response = await fetch(issuer.replace(/\/$/, '') + '/.well-known/openid-configuration')
  if (!response.ok) throw new Error('Provider SSO non raggiungibile')
  const doc = await response.json()
  if (!doc.authorization_endpoint || !doc.token_endpoint) throw new Error('Configurazione SSO incompleta')
  return doc
}

/** Build the authorization URL and remember what the callback must verify. */
export async function beginLogin(config: OidcConfig, navigate: (url: string) => void = url => window.location.assign(url)) {
  if (!config.issuer || !config.client_id) throw new Error('SSO non configurato: mancano issuer o client_id')
  const discovery = await discover(config.issuer)
  const state = randomString()
  const nonce = randomString()
  const verifier = randomString(48)
  const challenge = await sha256(verifier)
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ state, nonce, verifier, token_endpoint: discovery.token_endpoint }))

  const url = new URL(discovery.authorization_endpoint)
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('client_id', config.client_id)
  url.searchParams.set('redirect_uri', redirectUri())
  url.searchParams.set('scope', SCOPE)
  url.searchParams.set('state', state)
  url.searchParams.set('nonce', nonce)
  url.searchParams.set('code_challenge', challenge)
  url.searchParams.set('code_challenge_method', 'S256')
  navigate(url.toString())
}

function decodePayload(jwt: string): Record<string, unknown> {
  const part = jwt.split('.')[1] ?? ''
  const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
  return JSON.parse(json)
}

/** True when the current URL is the provider's redirect back to us. */
export function isCallback(search: string = window.location.search): boolean {
  const params = new URLSearchParams(search)
  return params.has('code') && params.has('state')
}

/**
 * Exchange the code, verify nonce, hand the id_token to the backend.
 * Returns the Ermes user. Always clears the one-shot state, and removes the
 * code from the address bar so a reload does not replay it.
 */
export async function completeLogin(config: OidcConfig, search: string = window.location.search): Promise<{ username: string; role: string }> {
  const params = new URLSearchParams(search)
  const stored = sessionStorage.getItem(STORAGE_KEY)
  sessionStorage.removeItem(STORAGE_KEY)
  window.history.replaceState(null, '', window.location.pathname)
  if (params.get('error')) throw new Error('Il provider SSO ha rifiutato l\'accesso: ' + (params.get('error_description') ?? params.get('error')))
  if (!stored) throw new Error('Sessione SSO non avviata da questo browser')
  const { state, nonce, verifier, token_endpoint } = JSON.parse(stored)
  if (params.get('state') !== state) throw new Error('Risposta SSO non corrispondente alla richiesta')
  if (!config.client_id) throw new Error('SSO non configurato')

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code: params.get('code') ?? '',
    redirect_uri: redirectUri(),
    client_id: config.client_id,
    code_verifier: verifier,
  })
  const tokenResponse = await fetch(token_endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!tokenResponse.ok) throw new Error('Scambio del codice SSO fallito')
  const tokens = await tokenResponse.json()
  const idToken: string = tokens.id_token
  if (!idToken) throw new Error('Il provider non ha restituito un id_token')
  if (decodePayload(idToken).nonce !== nonce) throw new Error('id_token non corrisponde alla richiesta (nonce)')

  const session = await fetch('/api/auth/oidc/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: idToken }),
    credentials: 'include',
  })
  if (!session.ok) throw new Error('Il server ha rifiutato il token SSO')
  return session.json()
}
