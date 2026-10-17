/**
 * Il segno di Ermes: una "E" i cui bracci sono righe di testo, come un documento,
 * e un puntino accanto al braccio centrale, il segnaposto di una citazione.
 * Racconta il prodotto in un segno: righe di un documento, e il punto da cui
 * una risposta rimanda alla sua fonte.
 *
 * Stessa geometria di `public/favicon.svg` e delle icone dell'app installabile.
 */
export function BrandMark({ className = 'h-10 w-10', title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      <rect width="64" height="64" rx="15" fill="#0f6cbd" />
      <rect x="17" y="16" width="8" height="32" rx="4" fill="#fff" />
      <rect x="17" y="16" width="30" height="7" rx="3.5" fill="#fff" />
      <rect x="17" y="28.5" width="21" height="7" rx="3.5" fill="#fff" />
      <rect x="17" y="41" width="30" height="7" rx="3.5" fill="#fff" />
      <circle cx="46.5" cy="32" r="4" fill="#a8d3fb" />
    </svg>
  )
}
