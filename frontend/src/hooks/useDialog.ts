import { useEffect, useRef } from 'react'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function isVisible(el: HTMLElement): boolean {
  const style = window.getComputedStyle(el)
  return style.display !== 'none' && style.visibility !== 'hidden'
}

/**
 * Comportamento da tastiera di una finestra modale.
 *
 * Quando si apre il focus entra nella finestra (prima non lo faceva: chi usa la
 * tastiera o un lettore di schermo restava sul pulsante sotto, dietro lo sfondo
 * scuro); Tab e Maiusc+Tab restano dentro finché è aperta; Esc la chiude; alla
 * chiusura il focus torna dov'era.
 *
 * Uso: `const ref = useDialog<HTMLDivElement>(isOpen, close)` e sull'elemento
 * della finestra `ref={ref} role="dialog" aria-modal="true" tabIndex={-1}`.
 */
export function useDialog<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T>(null)
  const closeRef = useRef(onClose)
  useEffect(() => {
    closeRef.current = onClose
  })

  useEffect(() => {
    if (!open) return
    const node = ref.current
    if (!node) return
    const previous = document.activeElement as HTMLElement | null
    node.focus()

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        closeRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(isVisible)
      if (items.length === 0) {
        event.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || active === node)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus?.()
    }
  }, [open])

  return ref
}
