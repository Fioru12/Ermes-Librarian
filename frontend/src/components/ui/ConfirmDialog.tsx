import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { Button } from './Button'

/**
 * A confirmation dialog in the application's own style, replacing the six
 * native `window.confirm` calls (delete document/library/source, revoke
 * access, remove synonym, enable cloud AI). The native one cannot be styled,
 * blocks the event loop, and in the Escape handling of the citation modal
 * produced two overlapping "modals" with different keyboard behaviour.
 *
 *   const confirm = useConfirm()
 *   if (!(await confirm({ title: 'Eliminare?', message: '...', danger: true }))) return
 *
 * Without a ConfirmProvider above (a component rendered on its own in a
 * test) the hook falls back to window.confirm, so existing tests that stub
 * it keep their meaning.
 */

export type ConfirmOptions = {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}

type Ask = (options: ConfirmOptions) => Promise<boolean>

const ConfirmContext = createContext<Ask | null>(null)

export function useConfirm(): Ask {
  const ask = useContext(ConfirmContext)
  return ask ?? (async options => window.confirm(options.title + '\n\n' + options.message))
}

type Pending = ConfirmOptions & { resolve: (value: boolean) => void }

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null)
  const { t } = useTheme()
  const confirmButton = useRef<HTMLButtonElement>(null)

  const ask = useCallback<Ask>(options => new Promise<boolean>(resolve => setPending({ ...options, resolve })), [])

  const settle = useCallback((value: boolean) => {
    setPending(current => {
      current?.resolve(value)
      return null
    })
  }, [])

  useEffect(() => {
    if (!pending) return
    confirmButton.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') settle(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pending, settle])

  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      {pending && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm animate-fadeIn"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ermes-confirm-title"
          onClick={event => {
            if (event.target === event.currentTarget) settle(false)
          }}
        >
          <section className={`w-full max-w-md rounded-2xl border p-6 shadow-2xl ${t.card}`}>
            <div className="flex items-start gap-3">
              <div className={`mt-0.5 rounded-lg p-2 ${pending.danger ? 'bg-rose-500/10 text-rose-400' : 'bg-blue-500/10 text-blue-400'}`}>
                <AlertTriangle className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <h2 id="ermes-confirm-title" className={`text-base font-semibold ${t.cardTitle}`}>{pending.title}</h2>
                <p className={`mt-2 text-sm leading-6 ${t.cardDesc}`}>{pending.message}</p>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => settle(false)}>{pending.cancelLabel ?? 'Annulla'}</Button>
              <Button ref={confirmButton} variant={pending.danger ? 'danger' : 'primary'} onClick={() => settle(true)}>
                {pending.confirmLabel ?? 'Conferma'}
              </Button>
            </div>
          </section>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}
