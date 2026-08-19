import { ReactNode } from 'react'
import { AlertTriangle, CheckCircle, X } from 'lucide-react'

interface NotificationProps {
  message: string
  type?: 'success' | 'error'
  onClose?: () => void
}

export function Notification({ message, type = 'success', onClose }: NotificationProps) {
  const bg = type === 'error'
    ? 'bg-rose-950/90 text-rose-200 border-rose-800'
    : 'bg-emerald-950/90 text-emerald-200 border-emerald-800'

  return (
    <div className={`absolute top-4 right-4 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-lg border transition duration-300 ${bg}`}>
      {type === 'error' ? <AlertTriangle className="w-4 h-4 shrink-0" /> : <CheckCircle className="w-4 h-4 shrink-0" />}
      <span className="text-sm font-medium">{message}</span>
      {onClose && (
        <button onClick={onClose} className="ml-2 opacity-60 hover:opacity-100 transition">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}

interface BadgeProps {
  children: ReactNode
  color?: 'blue' | 'emerald' | 'amber' | 'rose' | 'purple'
  className?: string
}

const badgeColors = {
  blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  rose: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  purple: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
}

export function Badge({ children, color = 'blue', className = '' }: BadgeProps) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${badgeColors[color]} ${className}`}>
      {children}
    </span>
  )
}
