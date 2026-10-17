import { useTheme } from '../../hooks/useTheme'

/**
 * Scheletro mostrato mentre una scheda viene caricata: la forma della pagina
 * che sta per arrivare invece di una riga di testo. Il testo "Caricamento…" resta
 * per i lettori di schermo (e per i test che aspettano che sparisca).
 */
export function PanelSkeleton() {
  const { t } = useTheme()
  const bar = `rounded-lg ${t.skeleton}`
  return (
    <div role="status" aria-busy="true" className="mx-auto w-full max-w-5xl space-y-6 p-6 md:p-8">
      <span className="sr-only">Caricamento…</span>
      <div className={`h-7 w-56 ${bar}`} />
      <div className={`h-4 w-full max-w-xl ${bar}`} />
      <div className="grid gap-4 md:grid-cols-2">
        <div className={`h-32 rounded-2xl ${t.skeleton}`} />
        <div className={`h-32 rounded-2xl ${t.skeleton}`} />
        <div className={`h-32 rounded-2xl ${t.skeleton} md:col-span-2`} />
      </div>
    </div>
  )
}
