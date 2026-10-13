import { InputHTMLAttributes, useId } from 'react'
import { useTheme } from '../../hooks/useTheme'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
}

// L'etichetta e' collegata al campo con htmlFor/id. Prima era solo vicina:
// a schermo si leggeva "Nome", ma un lettore di schermo annunciava soltanto
// "campo di testo", e cliccare l'etichetta non metteva il cursore nel campo.
export function Input({ label, className = '', id, ...props }: InputProps) {
  const { t } = useTheme()
  const generated = useId()
  const inputId = id ?? generated
  return (
    <div className="space-y-1">
      {label && <label htmlFor={inputId} className="text-xs font-semibold text-slate-400 block">{label}</label>}
      <input id={inputId} className={`w-full border rounded-lg px-3 py-2 text-sm outline-none transition ${t.sidebarInput} ${className}`} {...props} />
    </div>
  )
}

interface SelectProps extends InputHTMLAttributes<HTMLSelectElement> {
  label?: string
  children: React.ReactNode
}

export function Select({ label, children, className = '', id, ...props }: SelectProps) {
  const { t } = useTheme()
  const generated = useId()
  const selectId = id ?? generated
  return (
    <div className="space-y-1">
      {label && <label htmlFor={selectId} className="text-xs font-semibold text-slate-400 block">{label}</label>}
      <select id={selectId} className={`w-full border rounded-lg px-3 py-2 text-sm outline-none cursor-pointer transition ${t.sidebarInput} ${className}`} {...props}>
        {children}
      </select>
    </div>
  )
}
