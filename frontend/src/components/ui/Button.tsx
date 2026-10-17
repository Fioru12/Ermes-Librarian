import { ButtonHTMLAttributes, ReactNode, forwardRef } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'success'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  children: ReactNode
}

const variantClasses: Record<Variant, string> = {
  primary: 'bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white shadow-lg shadow-blue-900/30',
  secondary: 'border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-white/5 text-slate-600 dark:text-slate-300',
  danger: 'border border-rose-500/30 hover:bg-rose-500/10 text-rose-400',
  ghost: 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300',
  success: 'bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white shadow-lg shadow-emerald-900/30',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', children, className = '', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={`rounded-xl px-4 py-2 text-sm font-semibold transition cursor-pointer flex items-center justify-center gap-2 ${variantClasses[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
})
