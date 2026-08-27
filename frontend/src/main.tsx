import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// ── Global fetch wrapper ──────────────────────────────────────────────
// Vite dev-server proxies /api, /health, etc. to the backend on port 8502.
// Without `credentials: 'include'` (or 'same-origin') the session cookie
// that login sets is never forwarded → every protected route 401.
// This wrapper guarantees it for every same-origin request, so individual
// fetch() calls don't each have to repeat the option.
const _originalFetch: typeof window.fetch = window.fetch
window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const opts: RequestInit = init ?? {}
  if (typeof input === 'string' && input.startsWith('/')) {
    opts.credentials = (opts.credentials as RequestCredentials | undefined) || 'include'
  }
  return _originalFetch(input, opts)
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
