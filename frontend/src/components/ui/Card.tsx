import { ReactNode } from 'react'
import { useTheme } from '../../hooks/useTheme'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  className?: string
  onClick?: () => void
}

export function Card({ children, className = '', onClick, ...props }: CardProps) {
  const { t } = useTheme()
  return (
    <div className={`border p-6 rounded-2xl ${t.card} ${className}`} onClick={onClick} {...props}>
      {children}
    </div>
  )
}

interface CardTitleProps extends React.HTMLAttributes<HTMLHeadingElement> {
  children: ReactNode
  className?: string
}

export function CardTitle({ children, className = '', ...props }: CardTitleProps) {
  return (
    <h3 className={`text-sm font-bold uppercase tracking-wider flex items-center gap-2 text-slate-300 ${className}`} {...props}>
      {children}
    </h3>
  )
}
