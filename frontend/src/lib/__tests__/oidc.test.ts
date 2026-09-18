/**
 * The browser half of SSO, without a provider: what we send to the
 * authorization endpoint, and what we accept back.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { beginLogin, completeLogin, isCallback } from '../oidc'

const CONFIG = { enabled: true, issuer: 'https://idp.example/realms/ermes', client_id: 'ermes-spa' }
const DISCOVERY = {
  authorization_endpoint: 'https://idp.example/auth',
  token_endpoint: 'https://idp.example/token',
}

function jwtWith(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) => btoa(JSON.stringify(o)).replace(/=+$/, '')
  return b64({ alg: 'RS256' }) + '.' + b64(payload) + '.sig'
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  sessionStorage.clear()
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('beginLogin', () => {
  it('redirects to the authorization endpoint with PKCE, state and nonce, and remembers them', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(DISCOVERY)))
    const navigate = vi.fn()

    await beginLogin(CONFIG, navigate)

    expect(fetchMock.mock.calls[0][0]).toBe('https://idp.example/realms/ermes/.well-known/openid-configuration')
    const url = new URL(navigate.mock.calls[0][0])
    expect(url.origin + url.pathname).toBe('https://idp.example/auth')
    expect(url.searchParams.get('response_type')).toBe('code')
    expect(url.searchParams.get('client_id')).toBe('ermes-spa')
    expect(url.searchParams.get('redirect_uri')).toBe(window.location.origin + '/')
    expect(url.searchParams.get('scope')).toBe('openid profile email')
    expect(url.searchParams.get('code_challenge_method')).toBe('S256')
    expect(url.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/)

    const stored = JSON.parse(sessionStorage.getItem('ermes_oidc_login')!)
    expect(url.searchParams.get('state')).toBe(stored.state)
    expect(url.searchParams.get('nonce')).toBe(stored.nonce)
    expect(stored.token_endpoint).toBe('https://idp.example/token')
    // No secret anywhere in the request: this is a public client.
    expect(url.toString()).not.toMatch(/secret/i)
  })

  it('refuses to start without issuer or client_id', async () => {
    await expect(beginLogin({ enabled: true }, vi.fn())).rejects.toThrow(/issuer o client_id/)
  })
})

describe('completeLogin', () => {
  function armed(overrides: Partial<{ state: string; nonce: string; verifier: string }> = {}) {
    sessionStorage.setItem('ermes_oidc_login', JSON.stringify({
      state: 'st-1', nonce: 'no-1', verifier: 'ver-1', token_endpoint: DISCOVERY.token_endpoint, ...overrides,
    }))
  }

  it('exchanges the code with the verifier, checks the nonce, and hands the id_token to the backend', async () => {
    armed()
    const idToken = jwtWith({ sub: 'anna', nonce: 'no-1' })
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ id_token: idToken })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ username: 'anna', role: 'editor' })))

    const user = await completeLogin(CONFIG, '?code=abc&state=st-1')

    expect(user).toEqual({ username: 'anna', role: 'editor' })
    const [tokenUrl, tokenInit] = fetchMock.mock.calls[0]
    expect(tokenUrl).toBe('https://idp.example/token')
    const form = new URLSearchParams(String(tokenInit.body))
    expect(form.get('grant_type')).toBe('authorization_code')
    expect(form.get('code')).toBe('abc')
    expect(form.get('code_verifier')).toBe('ver-1')
    expect(form.get('client_id')).toBe('ermes-spa')
    const [sessionUrl, sessionInit] = fetchMock.mock.calls[1]
    expect(sessionUrl).toBe('/api/auth/oidc/session')
    expect(JSON.parse(String(sessionInit.body))).toEqual({ id_token: idToken })
    expect(sessionInit.credentials).toBe('include')
    // One-shot: the state cannot be replayed.
    expect(sessionStorage.getItem('ermes_oidc_login')).toBeNull()
  })

  it('rejects a callback whose state does not match', async () => {
    armed()
    await expect(completeLogin(CONFIG, '?code=abc&state=forged')).rejects.toThrow(/non corrispondente/)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects an id_token carrying a different nonce before it reaches the backend', async () => {
    armed()
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ id_token: jwtWith({ nonce: 'other' }) })))
    await expect(completeLogin(CONFIG, '?code=abc&state=st-1')).rejects.toThrow(/nonce/)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reports a provider error instead of trying to exchange nothing', async () => {
    armed()
    await expect(completeLogin(CONFIG, '?error=access_denied&error_description=No&state=st-1')).rejects.toThrow(/rifiutato/)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refuses a callback the browser never started', async () => {
    await expect(completeLogin(CONFIG, '?code=abc&state=st-1')).rejects.toThrow(/non avviata/)
  })
})

describe('isCallback', () => {
  it('needs both code and state', () => {
    expect(isCallback('?code=x&state=y')).toBe(true)
    expect(isCallback('?code=x')).toBe(false)
    expect(isCallback('')).toBe(false)
  })
})
