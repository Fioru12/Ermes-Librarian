import { InputHTMLAttributes } from 'react'
import { useTheme } from '../../hooks/useTheme'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
}

export function Input({ label, className = '', ...props }: InputProps) {
  const { t } = useTheme()
  return (
    <div className="space-y-1">
      {label && <label className="text-xs font-semibold text-slate-400 block">{label}</label>}
      <input className={`w-full border rounded-lg px-3 py-2 text-sm outline-none transition ${t.sidebarInput} ${className}`} {...props} />
    </div>
  )
}

interface SelectProps extends InputHTMLAttributes<HTMLSelectElement> {
  label?: string
  children: React.ReactNode
}

export function Select({ label, children, className = '', ...props }: SelectProps) {
  const { t } = useTheme()
  return (
    <div className="space-y-1">
      {label && <label className="text-xs font-semibold text-slate-400 block">{label}</label>}
      <select className={`w-full border rounded-lg px-3 py-2 text-sm outline-none cursor-pointer transition ${t.sidebarInput} ${className}`} {...props}>
        {children}
      </select>
    </div>
  )
}
