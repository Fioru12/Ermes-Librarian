/**
 * App: authentication gate and the SSE answer stream.
 *
 * Until 18 September 2026 nothing tested App at all: the login gate, the
 * fetch to /ask/stream and the SSE parsing were covered only by the E2E
 * specs — which skipped themselves in CI. These tests drive App with a
 * mocked fetch and a hand-built ReadableStream, so the parsing of the
 * status / citations / answer / done events and the abort path are pinned
 * without a browser or a backend.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

type Route = (init?: RequestInit) => Response | Promise<Response>

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function sse(events: Array<[string, unknown]>, chunking: 'whole' | 'split' = 'whole'): Response {
  const text = events.map(([type, data]) => 'event: ' + type + '\ndata: ' + JSON.stringify(data) + '\n\n').join('')
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      if (chunking === 'whole') {
        controller.enqueue(encoder.encode(text))
      } else {
        // Split in the middle of an event: the client must buffer across reads.
        const cut = Math.floor(text.length / 2)
        controller.enqueue(encoder.encode(text.slice(0, cut)))
        controller.enqueue(encoder.encode(text.slice(cut)))
      }
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

let routes: Record<string, Route>
let calls: Array<{ url: string; init?: RequestInit }>

beforeEach(() => {
  calls = []
  routes = {
    '/api/auth/me': () => json({ username: 'anna', role: 'viewer' }),
    '/api/auth/oidc/config': () => json({ enabled: false }),
    '/api/libraries': () => json({ items: [{ id: 'hr', name: 'Procedure HR', document_count: 2 }] }),
    '/health': () => json({ status: 'healthy', warnings: [] }),
  }
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    calls.push({ url, init })
    const route = routes[url] ?? routes[url.split('?')[0]]
    if (!route) return new Response('not found', { status: 404 })
    return route(init)
  }))
  localStorage.setItem('ermes_onboarding_dismissed', '1')
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

async function renderAuthenticated() {
  render(<App />)
  await screen.findByPlaceholderText(/fai una domanda/i)
  await waitFor(() => expect(screen.getAllByText('Procedure HR').length).toBeGreaterThan(0))
}

async function ask(question: string) {
  const input = screen.getByPlaceholderText(/fai una domanda/i)
  fireEvent.change(input, { target: { value: question } })
  fireEvent.submit(input.closest('form')!)
}

const CITATION = { document_id: 'd1', filename: 'policy-ferie.md', locator: 'Sezione: Ferie', excerpt: '15 giorni' }
const ANSWER = 'Le ferie vanno richieste con 15 giorni di anticipo.'

describe('App — authentication gate', () => {
  it('shows the login form when the session is anonymous, then logs in', async () => {
    routes['/api/auth/me'] = () => json({ detail: 'no' }, 401)
    routes['/api/auth/login'] = () => json({ username: 'capo', role: 'admin' })
    render(<App />)

    const user = await screen.findByPlaceholderText(/nome utente/i)
    fireEvent.change(user, { target: { value: 'capo' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'Segreta!123' } })
    fireEvent.click(screen.getByRole('button', { name: /^accedi/i }))

    await screen.findByPlaceholderText(/fai una domanda/i)
    const login = calls.find(c => c.url === '/api/auth/login')!
    expect(login.init?.credentials).toBe('include')
    expect(JSON.parse(String(login.init?.body))).toEqual({ username: 'capo', password: 'Segreta!123' })
  })

  it('reports a rejected login without leaving the form', async () => {
    routes['/api/auth/me'] = () => json({}, 401)
    routes['/api/auth/login'] = () => json({ detail: 'Credenziali non valide' }, 401)
    render(<App />)
    fireEvent.change(await screen.findByPlaceholderText(/nome utente/i), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: /^accedi/i }))

    await screen.findByText(/credenziali non valide/i)
    expect(screen.getByPlaceholderText(/nome utente/i)).toBeInTheDocument()
  })
})

describe('App — SSE answer stream', () => {
  it('renders status steps, then the final answer with its citations', async () => {
    routes['/api/libraries/hr/ask/stream'] = () => sse([
      ['status', { step: 'retrieving' }],
      ['citations', { citations: [CITATION] }],
      ['answer', { chunk: ANSWER }],
      ['done', { answer_id: 'srv-1', answer: ANSWER, citations: [CITATION], evidence: { status: 'supported' }, meta: {} }],
    ], 'split')
    await renderAuthenticated()

    await ask('Con quanto anticipo chiedo le ferie?')

    await screen.findByText(ANSWER)
    expect(screen.getAllByText(/policy-ferie\.md/).length).toBeGreaterThan(0)
    // The stream is over: no status label lingers, the input is usable again.
    expect(screen.queryByText(/ricerca evidenze/i)).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByPlaceholderText(/fai una domanda/i)).not.toBeDisabled())

    const req = calls.find(c => c.url === '/api/libraries/hr/ask/stream')!
    expect(req.init?.method).toBe('POST')
    expect(JSON.parse(String(req.init?.body))).toEqual({ question: 'Con quanto anticipo chiedo le ferie?', history: [] })
  })

  it('accumulates multiple answer chunks progressively during stream', async () => {
    routes['/api/libraries/hr/ask/stream'] = () => sse([
      ['status', { step: 'retrieving' }],
      ['answer', { chunk: 'Prima parte ' }],
      ['answer', { chunk: 'seconda parte.' }],
      ['done', { answer_id: 'srv-2', answer: 'Prima parte seconda parte.', citations: [], evidence: { status: 'supported' }, meta: {} }],
    ], 'split')
    await renderAuthenticated()

    await ask('Domanda sui chunk?')

    await screen.findByText('Prima parte seconda parte.')
  })

  it('sends only the last three user questions as history, never the answers', async () => {
    const bodies: Array<{ history: unknown }> = []
    routes['/api/libraries/hr/ask/stream'] = init => {
      bodies.push(JSON.parse(String(init?.body)))
      return sse([['done', { answer: 'ok', citations: [], evidence: { status: 'supported' } }]])
    }
    await renderAuthenticated()
    const questions = ['prima', 'seconda', 'terza', 'quarta']
    for (const [index, q] of questions.entries()) {
      await ask(q)
      await waitFor(() => expect(bodies.length).toBe(index + 1))
      await waitFor(() => expect(screen.getByPlaceholderText(/fai una domanda/i)).not.toBeDisabled())
    }
    expect(bodies[3].history).toEqual([{ question: 'prima' }, { question: 'seconda' }, { question: 'terza' }])
  })

  it('Stop aborts the request and says so in the transcript', async () => {
    let abortSignal: AbortSignal | null | undefined
    routes['/api/libraries/hr/ask/stream'] = init => {
      abortSignal = init?.signal
      return new Promise<Response>((_, reject) => {
        abortSignal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    }
    await renderAuthenticated()
    await ask('domanda lunga')

    const stop = await screen.findByRole('button', { name: /stop/i })
    await act(async () => { fireEvent.click(stop) })

    await screen.findByText('Richiesta annullata.')
    expect(abortSignal?.aborted).toBe(true)
    await waitFor(() => expect(screen.getByPlaceholderText(/fai una domanda/i)).not.toBeDisabled())
  })

  it('a failed request leaves a readable message, not an empty bubble', async () => {
    routes['/api/libraries/hr/ask/stream'] = () => json({ detail: 'boom' }, 500)
    await renderAuthenticated()
    await ask('qualsiasi')
    await screen.findByText(/non riesco a completare la richiesta/i)
  })
})

describe('App — logout and SSO', () => {
  it('Esci ends the server session and returns to the login form', async () => {
    routes['/api/auth/logout'] = () => json({ ok: true })
    await renderAuthenticated()

    fireEvent.click(screen.getByRole('button', { name: /esci/i }))

    await screen.findByPlaceholderText(/nome utente/i)
    const logout = calls.find(c => c.url === '/api/auth/logout')!
    expect(logout.init?.method).toBe('POST')
    expect(logout.init?.credentials).toBe('include')
  })

  it('the SSO button starts the provider flow instead of showing a notification', async () => {
    routes['/api/auth/me'] = () => json({}, 401)
    routes['/api/auth/oidc/config'] = () => json({ enabled: true, issuer: 'https://idp.example', client_id: 'ermes-spa' })
    routes['https://idp.example/.well-known/openid-configuration'] = () =>
      json({ authorization_endpoint: 'https://idp.example/auth', token_endpoint: 'https://idp.example/token' })
    const assign = vi.fn()
    const original = window.location
    Object.defineProperty(window, 'location', { configurable: true, value: { ...original, assign, origin: original.origin, search: '', pathname: '/' } })
    try {
      render(<App />)
      fireEvent.click(await screen.findByRole('button', { name: /accedi con sso/i }))
      await waitFor(() => expect(assign).toHaveBeenCalledTimes(1))
      expect(String(assign.mock.calls[0][0])).toMatch(/^https:\/\/idp\.example\/auth\?.*code_challenge_method=S256/)
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: original })
    }
  })

  it('coming back from the provider completes the login without showing the form', async () => {
    routes['/api/auth/oidc/config'] = () => json({ enabled: true, issuer: 'https://idp.example', client_id: 'ermes-spa' })
    const idToken = btoa('{}') + '.' + btoa(JSON.stringify({ nonce: 'no-1' })).replace(/=+$/, '') + '.sig'
    routes['https://idp.example/token'] = () => json({ id_token: idToken })
    routes['/api/auth/oidc/session'] = () => json({ username: 'anna', role: 'editor' })
    sessionStorage.setItem('ermes_oidc_login', JSON.stringify({ state: 'st-1', nonce: 'no-1', verifier: 'v', token_endpoint: 'https://idp.example/token' }))
    window.history.replaceState(null, '', '/?code=abc&state=st-1')
    try {
      render(<App />)
      await screen.findByPlaceholderText(/fai una domanda/i)
      expect(calls.some(c => c.url === '/api/auth/me')).toBe(false)
      expect(window.location.search).toBe('')
    } finally {
      window.history.replaceState(null, '', '/')
      sessionStorage.clear()
    }
  })
})

