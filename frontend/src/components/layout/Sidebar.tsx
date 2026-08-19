import { Sun, Moon, MessageSquare, FileText, Activity, Settings, Users, Shield, RefreshCw, Sparkles } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import type { TabId } from '../../types'

interface SidebarProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
  healthStatus?: { status: string }
  onRefresh: () => void
  isAdmin?: boolean
  username?: string
}

const navItems: { tab: TabId; icon: typeof MessageSquare; label: string; admin?: boolean }[] = [
  { tab: 'chat', icon: MessageSquare, label: 'Assistente' },
  { tab: 'docs', icon: FileText, label: 'Biblioteche e documenti' },
  { tab: 'health', icon: Activity, label: 'Stato Sistema' },
  { tab: 'settings', icon: Settings, label: 'Impostazioni' },
  { tab: 'admin-users', icon: Users, label: 'Accessi e chiavi API', admin: true },
  { tab: 'admin-audit', icon: Shield, label: 'Audit Log', admin: true },
]

export default function Sidebar({ activeTab, onTabChange, healthStatus, onRefresh, isAdmin = false, username }: SidebarProps) {
  const { isDark, toggle, t } = useTheme()
  const visibleNavItems = navItems.filter(item => !item.admin || isAdmin)

  return (
    <aside className={`w-[17.5rem] border-r flex flex-col z-10 transition-colors duration-200 ${t.sidebar}`}>
      {/* Title */}
      <div className="px-5 pt-6 pb-5 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-400 via-blue-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-blue-500/30 ring-1 ring-white/10">
          <span className="text-white font-bold text-base">E</span>
        </div>
        <div>
          <h1 className={`text-base font-semibold tracking-tight ${t.sidebarTitle}`}>ERMES</h1>
          <p className={`text-[10px] mt-0.5 ${t.sidebarLabel} font-medium uppercase tracking-[0.16em]`}>Knowledge</p>
        </div>
      </div>

      {/* Config Section */}
      <div className="px-4 pb-5 flex-1 flex flex-col gap-6 overflow-y-auto">
        {/* Library-first AI policy */}
        <div className="space-y-2 rounded-xl border border-white/[0.06] bg-white/[0.025] p-3">
          <label className={`text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 ${t.sidebarLabel}`}>
            <Shield className="w-3.5 h-3.5 text-purple-400" /> Assistente IA
          </label>
          <p className="text-xs leading-5 text-slate-400">La biblioteca scelta decide se usare solo evidenze, Ollama locale o un provider cloud approvato.</p>
        </div>

        {/* Navigation */}
        <nav className="flex flex-col gap-1 pt-1">
          {visibleNavItems.map((item) => (
            <button key={item.tab} onClick={() => onTabChange(item.tab)} aria-current={activeTab === item.tab ? 'page' : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${activeTab === item.tab ? t.navButtonActive : t.navButtonInactive}`}>
              <item.icon className={`w-4 h-4 ${activeTab === item.tab ? '' : 'opacity-70 group-hover:opacity-100 transition-opacity'}`} />
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Footer */}
      <div className={`p-4 border-t ${t.statusFooter}`}>
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-500/10 bg-emerald-500/[0.04] px-2.5 py-2 text-[11px] text-slate-400">
          <Sparkles className="h-3.5 w-3.5 text-blue-400" /><span className="truncate">Risposte con fonti verificabili</span>
        </div>
        <div className="flex items-center justify-between text-xs text-slate-400">
        <button onClick={toggle} className="flex items-center gap-1.5 hover:text-blue-500 font-semibold transition">
          {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-600" />}
          <span>{isDark ? 'Light' : 'Dark'}</span>
        </button>
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${healthStatus?.status === 'healthy' ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'}`} />
          <span className="font-medium text-slate-400">{healthStatus?.status === 'healthy' ? 'Attivo' : 'Pronto'}</span>
        </div>
        {username && <span className="max-w-20 truncate text-slate-500" title={username}>{username}</span>}
        <button onClick={onRefresh} title="Aggiorna stato" className="hover:text-blue-500 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
        </div>
      </div>
    </aside>
  )
}
