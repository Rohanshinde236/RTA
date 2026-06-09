import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import {
  LayoutDashboard, Globe, Settings, List, ScrollText, MessageSquare, Monitor, Sun, Moon
} from 'lucide-react'

const NAV = [
  { to: '/',               icon: LayoutDashboard, label: 'Dashboard'        },
  { to: '/regions',        icon: Globe,           label: 'Regions'          },
  { to: '/agent-settings', icon: Settings,        label: 'Agent Settings'   },
  { to: '/thresholds',     icon: List,            label: 'Skill Thresholds' },
  { to: '/logs',           icon: ScrollText,      label: 'Live Logs'        },
  { to: '/chatbot',        icon: MessageSquare,   label: 'Chatbot'          },
]

export default function Sidebar() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('rta-theme')
    return saved ? saved === 'dark' : true   // default = dark
  })

  useEffect(() => {
    const root = document.documentElement
    if (dark) {
      root.classList.remove('light-mode')
      localStorage.setItem('rta-theme', 'dark')
    } else {
      root.classList.add('light-mode')
      localStorage.setItem('rta-theme', 'light')
    }
  }, [dark])

  return (
    <aside className="flex flex-col w-56 min-w-[224px] bg-[#0d1526] border-r border-[#1e3354]">
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-[#1e3354]">
        <span className="text-2xl">📊</span>
        <div>
          <div className="text-sm font-bold text-white leading-tight">RTA Monitor</div>
          <div className="text-[10px] text-slate-500 uppercase tracking-widest">Real-Time Analyst</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ` +
              (isActive
                ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
                : 'text-slate-400 hover:bg-[#162540] hover:text-slate-200')
            }
          >
            <Icon size={16} strokeWidth={1.8} />
            {label}
          </NavLink>
        ))}

        {/* Divider */}
        <div className="pt-2 mt-2 border-t border-[#1e3354] space-y-1">
          {/* CMS Portal */}
          <a
            href="/portal/cms"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 text-slate-400 hover:bg-[#162540] hover:text-slate-200"
          >
            <Monitor size={16} strokeWidth={1.8} />
            CMS Portal
            <span className="ml-auto text-[9px] text-slate-600 border border-slate-700 rounded px-1">↗</span>
          </a>

          {/* Theme toggle */}
          <button
            onClick={() => setDark(d => !d)}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 text-slate-400 hover:bg-[#162540] hover:text-slate-200"
          >
            {dark
              ? <><Sun  size={16} strokeWidth={1.8} /><span>Light Mode</span></>
              : <><Moon size={16} strokeWidth={1.8} /><span>Dark Mode</span></>
            }
            <span className={`ml-auto w-8 h-4 rounded-full transition-colors relative ${dark ? 'bg-slate-700' : 'bg-blue-600'}`}>
              <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${dark ? 'translate-x-0.5' : 'translate-x-4'}`} />
            </span>
          </button>
        </div>
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-[#1e3354]">
        <div className="text-[10px] text-slate-600 text-center">
          APJ-IN · APJ-CN · APJ-AU · EMEA
        </div>
      </div>
    </aside>
  )
}
