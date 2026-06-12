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
    <aside className="flex flex-col w-56 min-w-[224px] border-r border-[#1e3354]"
      style={{background:'linear-gradient(180deg, #0d1829 0%, #080d1a 100%)'}}>
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-[#1e3354]">
        {/* Custom SVG Logo */}
        <div className="relative flex-shrink-0 w-10 h-10">
          <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
            {/* Outer gradient ring */}
            <circle cx="20" cy="20" r="18.5" stroke="url(#sb-ring)" strokeWidth="1.5" opacity="0.55"/>
            {/* Subtle inner glow */}
            <circle cx="20" cy="20" r="15" fill="url(#sb-bg)" opacity="0.07"/>
            {/* Bar 1 — short */}
            <rect x="7" y="25" width="5.5" height="8" rx="1.5" fill="url(#sb-b1)"/>
            {/* Bar 2 — medium */}
            <rect x="15" y="17" width="5.5" height="16" rx="1.5" fill="url(#sb-b2)"/>
            {/* Bar 3 — tall */}
            <rect x="23" y="9" width="5.5" height="24" rx="1.5" fill="url(#sb-b3)"/>
            {/* Trend line over bars */}
            <polyline
              points="9.75,24 17.75,16 25.75,8"
              stroke="#22d3ee"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {/* Glow at trend tip */}
            <circle cx="25.75" cy="8" r="2.8" fill="#22d3ee" opacity="0.3"/>
            <circle cx="25.75" cy="8" r="1.8" fill="#22d3ee"/>
            <defs>
              <linearGradient id="sb-ring" x1="2" y1="2" x2="38" y2="38" gradientUnits="userSpaceOnUse">
                <stop stopColor="#3b82f6"/>
                <stop offset="0.5" stopColor="#06b6d4"/>
                <stop offset="1" stopColor="#818cf8"/>
              </linearGradient>
              <linearGradient id="sb-bg" x1="0" y1="0" x2="1" y2="1">
                <stop stopColor="#3b82f6"/>
                <stop offset="1" stopColor="#06b6d4"/>
              </linearGradient>
              <linearGradient id="sb-b1" x1="0" y1="0" x2="0" y2="1">
                <stop stopColor="#60a5fa" stopOpacity="0.85"/>
                <stop offset="1" stopColor="#1e40af" stopOpacity="0.4"/>
              </linearGradient>
              <linearGradient id="sb-b2" x1="0" y1="0" x2="0" y2="1">
                <stop stopColor="#38bdf8"/>
                <stop offset="1" stopColor="#0369a1" stopOpacity="0.55"/>
              </linearGradient>
              <linearGradient id="sb-b3" x1="0" y1="0" x2="0" y2="1">
                <stop stopColor="#a78bfa"/>
                <stop offset="1" stopColor="#4338ca" stopOpacity="0.6"/>
              </linearGradient>
            </defs>
          </svg>
          {/* Animated live-pulse ring at trend tip (top-right) */}
          <span className="absolute top-0 right-0 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" style={{animationDuration:'2s'}}/>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500/0"/>
          </span>
        </div>
        <div>
          <div
            className="text-sm font-bold leading-tight tracking-wide"
            style={{
              background: 'linear-gradient(90deg, #e2e8f0 0%, #93c5fd 60%, #67e8f9 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            RTA Monitor
          </div>
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
        <div className="text-[10px] text-slate-600 text-center leading-relaxed">
          APJ-IN · APJ-CN · APJ-AU · EMEA<br/>
          APJ-HK · APJ-MY · APJ-KR · APJ-TH<br/>
          LATAM-BR · APJ-TW
        </div>
      </div>
    </aside>
  )
}
