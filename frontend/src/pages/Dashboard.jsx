import { useEffect, useState, useCallback } from 'react'
import { Play, Square, RotateCcw, AlertTriangle, ExternalLink, Monitor } from 'lucide-react'
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import { socket } from '../socket'

// live_state.json keys: "rta", "cn", "au", "emea", "hk", "my", "kr", "th", "br", "tw"
// SKILL_REGION_MAP values: "APJ-IN", "APJ-CN", "APJ-AU", "EMEA", "APJ-HK", "APJ-MY", "APJ-KR", "APJ-TH", "LATAM-BR", "APJ-TW"
const TAG_TO_APJ = {
  rta: 'APJ-IN', cn: 'APJ-CN', au: 'APJ-AU', emea: 'EMEA',
  hk: 'APJ-HK', my: 'APJ-MY', kr: 'APJ-KR', th: 'APJ-TH', br: 'LATAM-BR', tw: 'APJ-TW',
}

const REGIONS = [
  { tag: 'rta',  name: 'India',     flag: '🇮🇳', abbr: 'IN', portalUrl: '/portal/rta'  },
  { tag: 'cn',   name: 'China',     flag: '🇨🇳', abbr: 'CN', portalUrl: '/portal/cn'   },
  { tag: 'au',   name: 'Australia', flag: '🇦🇺', abbr: 'AU', portalUrl: '/portal/au'   },
  { tag: 'emea', name: 'EMEA',      flag: '🌍',  abbr: 'EM', portalUrl: '/portal/emea' },
  { tag: 'hk',   name: 'Hong Kong', flag: '🇭🇰', abbr: 'HK', portalUrl: '/portal/hk'   },
  { tag: 'my',   name: 'Malaysia',  flag: '🇲🇾', abbr: 'MY', portalUrl: '/portal/my'   },
  { tag: 'kr',   name: 'Korea',     flag: '🇰🇷', abbr: 'KR', portalUrl: '/portal/kr'   },
  { tag: 'th',   name: 'Thailand',  flag: '🇹🇭', abbr: 'TH', portalUrl: '/portal/th'   },
  { tag: 'br',   name: 'Brazil',    flag: '🇧🇷', abbr: 'BR', portalUrl: '/portal/br'   },
  { tag: 'tw',   name: 'Taiwan',    flag: '🇹🇼', abbr: 'TW', portalUrl: '/portal/tw'   },
]

function bandColor(band) {
  if (!band) return { text: 'text-slate-400', bg: 'bg-slate-700/40', border: 'border-slate-600' }
  const b = band.toUpperCase()
  if (b === 'EXCELLENT') return { text: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', glow: 'glow-green' }
  if (b === 'HEALTHY')   return { text: 'text-green-400',   bg: 'bg-green-500/10',   border: 'border-green-500/30',   glow: 'glow-green' }
  if (b === 'WARNING')   return { text: 'text-amber-400',   bg: 'bg-amber-500/10',   border: 'border-amber-500/30',   glow: 'glow-amber' }
  if (b === 'CRITICAL')  return { text: 'text-orange-400',  bg: 'bg-orange-500/10',  border: 'border-orange-500/30',  glow: 'glow-amber' }
  if (b === 'SEVERE')    return { text: 'text-red-400',     bg: 'bg-red-500/10',     border: 'border-red-500/30',     glow: 'glow-red'   }
  if (b === 'ACTIVE')    return { text: 'text-blue-400',    bg: 'bg-blue-500/10',    border: 'border-blue-500/30' }
  if (b === 'INACTIVE')  return { text: 'text-slate-500',   bg: 'bg-slate-700/30',   border: 'border-slate-600/40' }
  if (b === 'NO DATA')   return { text: 'text-slate-500',   bg: 'bg-slate-700/30',   border: 'border-slate-600/40' }
  return { text: 'text-slate-400', bg: 'bg-slate-700/40', border: 'border-slate-600' }
}

function RegionCard({ region, liveState, isRunning, configRegion, configSkillCount, portalUrl }) {
  // live_state is structured as: liveState["rta"] = { skills: { TS_CSTCE: {...}, ... }, last_poll_time, ... }
  const regionData  = liveState?.[region.tag]
  const skillsObj   = regionData?.skills || {}
  const liveSkills  = Object.entries(skillsObj).map(([name, v]) => ({ skill: name, ...v }))
  const hasLive     = liveSkills.length > 0

  // Compute SLA averages
  const slaValues  = liveSkills.map(s => s.sla).filter(x => x != null)
  const avgSla     = slaValues.length ? slaValues.reduce((a, b) => a + b, 0) / slaValues.length : null
  const worstSkill = hasLive ? [...liveSkills].sort((a, b) => (a.sla ?? 100) - (b.sla ?? 100))[0] : null
  const liveBand   = worstSkill?.band || (avgSla != null
    ? (avgSla >= 95 ? 'EXCELLENT' : avgSla >= 90 ? 'HEALTHY' : avgSla >= 80 ? 'WARNING' : avgSla >= 70 ? 'CRITICAL' : 'SEVERE')
    : null)

  // Badge logic — ONLY show live band when system is actually RUNNING
  //   stopped → always ACTIVE / INACTIVE from config (ignore stale live_state.json)
  //   running + live data → actual band (HEALTHY/WARNING/SEVERE etc.)
  //   running + no data yet → NO DATA
  const isActive = configRegion?.active !== false
  let badgeLabel, col
  if (!isRunning) {
    badgeLabel = isActive ? 'ACTIVE' : 'INACTIVE'
    col = bandColor(badgeLabel)
  } else if (isRunning && hasLive) {
    badgeLabel = liveBand || 'NO DATA'
    col = bandColor(liveBand)
  } else {
    badgeLabel = 'NO DATA'
    col = bandColor('NO DATA')
  }

  // Skills count: live when running, from config otherwise
  const skillCount = hasLive ? liveSkills.length : configSkillCount

  // Sparkline from top skills
  const sparkData = liveSkills.slice(0, 8).map((s, i) => ({ v: s.sla || 0, i }))

  const breachedCount = liveSkills.filter(s => s.breached).length
  const leverCount    = liveSkills.filter(s => s.lever_fired && s.lever_fired !== 'None').length

  // Fixed portal URL passed from parent
  const dashPortalUrl = portalUrl || null

  // Last poll time
  const pollTime = regionData?.last_poll_time

  return (
    <div className={`rta-card overflow-hidden animate-slide-in ${col.glow || ''}`}>
      {/* Card header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#111827] border border-[#1e3354] flex items-center justify-center text-xs font-bold text-slate-400">
            {region.abbr}
          </div>
          <div>
            <div className="font-semibold text-white text-sm">{region.name}</div>
            <div className="text-xs text-slate-500">
              {skillCount} skill{skillCount !== 1 ? 's' : ''} {hasLive ? 'monitored' : 'configured'}
              {pollTime && <span className="ml-2 text-slate-600">· {pollTime}</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {dashPortalUrl && (
            <a
              href={dashPortalUrl}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 border border-blue-500/25 hover:border-blue-500/50 px-2 py-1 rounded transition-colors"
            >
              <ExternalLink size={10} /> Dashboard
            </a>
          )}
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${col.text} ${col.bg} ${col.border}`}>
            {badgeLabel}
          </span>
        </div>
      </div>

      <div className="px-5 pb-4">
        {/* SLA number */}
        <div className="mb-2">
          <div className={`text-4xl font-bold tabular-nums ${isRunning && hasLive ? col.text : 'text-slate-600'}`}>
            {isRunning && avgSla != null ? `${avgSla.toFixed(1)}%` : '—'}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">Average SLA</div>
        </div>

        {/* Sparkline — only when running with live data */}
        {isRunning && sparkData.length > 1 && (
          <div className="h-10 mb-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sparkData}>
                <Line
                  type="monotone" dataKey="v"
                  stroke={liveBand === 'SEVERE' || liveBand === 'CRITICAL' ? '#ef4444' : '#10b981'}
                  strokeWidth={2} dot={false}
                />
                <Tooltip
                  contentStyle={{ background: '#111827', border: '1px solid #1e3354', borderRadius: 6, fontSize: 11 }}
                  formatter={v => [`${v}%`, 'SLA']}
                  labelFormatter={() => ''}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Stopped hint */}
        {!isRunning && (
          <div className="text-xs text-slate-600 italic mb-2">
            {isActive ? 'System stopped — start to see live SLA' : 'Region inactive — not being monitored'}
          </div>
        )}

        {/* Live stats row — only when running */}
        {isRunning && hasLive && (
          <div className="flex gap-3 text-xs mt-1 flex-wrap">
            {breachedCount > 0 && (
              <span className="flex items-center gap-1 text-red-400">
                <AlertTriangle size={11} /> {breachedCount} breached
              </span>
            )}
            {leverCount > 0 && (
              <span className="flex items-center gap-1 text-orange-400">
                ⚡ {leverCount} lever{leverCount > 1 ? 's' : ''}
              </span>
            )}
            {worstSkill && (
              <span className="text-slate-500 truncate">Worst: {worstSkill.skill} ({worstSkill.sla?.toFixed(1)}%)</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function HealthSummaryBar({ liveState, isRunning, configRegions, skillRegionMap }) {
  const total   = REGIONS.length
  const active  = configRegions.filter(r => r.active !== false).length
  const inactive = total - active

  if (!isRunning) {
    return (
      <div className="rta-card px-5 py-3 flex flex-wrap items-center gap-4 text-xs">
        <span className="font-semibold text-slate-400 uppercase tracking-wider">Health Summary</span>
        <span className="text-slate-500">{total} regions configured · {active} active · {inactive} inactive</span>
        <span className="text-slate-600 italic ml-auto">Start system to see live health</span>
      </div>
    )
  }

  // Aggregate live stats across all regions
  let totalSkills = 0, breachedTotal = 0, leverTotal = 0, slaSum = 0, slaCount = 0
  const bandCounts = { EXCELLENT: 0, HEALTHY: 0, WARNING: 0, CRITICAL: 0, SEVERE: 0 }

  REGIONS.forEach(r => {
    const rd = liveState?.[r.tag]
    if (!rd?.skills) return
    Object.values(rd.skills).forEach(s => {
      totalSkills++
      if (s.sla != null) { slaSum += s.sla; slaCount++ }
      if (s.breached) breachedTotal++
      if (s.lever_fired && s.lever_fired !== 'None') leverTotal++
      if (s.band && bandCounts[s.band] !== undefined) bandCounts[s.band]++
    })
  })

  const overallSla = slaCount ? (slaSum / slaCount).toFixed(1) : null
  const overallBand = overallSla != null
    ? (overallSla >= 95 ? 'EXCELLENT' : overallSla >= 90 ? 'HEALTHY' : overallSla >= 80 ? 'WARNING' : overallSla >= 70 ? 'CRITICAL' : 'SEVERE')
    : null
  const slaColor = overallBand === 'SEVERE' || overallBand === 'CRITICAL' ? 'text-red-400'
    : overallBand === 'WARNING' ? 'text-amber-400' : 'text-emerald-400'

  // Region health dots
  const regionDots = REGIONS.map(r => {
    const rd = liveState?.[r.tag]
    if (!rd?.skills) return { tag: r.tag, flag: r.flag, color: 'bg-slate-600', label: 'No data' }
    const skills = Object.values(rd.skills)
    const worstBand = skills.reduce((worst, s) => {
      const rank = { SEVERE: 5, CRITICAL: 4, WARNING: 3, HEALTHY: 2, EXCELLENT: 1 }
      return (rank[s.band] || 0) > (rank[worst] || 0) ? s.band : worst
    }, 'EXCELLENT')
    const dotColor = worstBand === 'SEVERE' ? 'bg-red-500' : worstBand === 'CRITICAL' ? 'bg-orange-500'
      : worstBand === 'WARNING' ? 'bg-amber-400' : 'bg-emerald-500'
    return { tag: r.tag, flag: r.flag, color: dotColor, label: worstBand }
  })

  return (
    <div className="rta-card px-5 py-3 flex flex-wrap items-center gap-4 text-xs">
      <span className="font-semibold text-slate-400 uppercase tracking-wider">Health Summary</span>

      {/* Overall SLA */}
      {overallSla && (
        <div className="flex items-center gap-1.5">
          <span className="text-slate-500">Overall SLA</span>
          <span className={`font-bold text-sm ${slaColor}`}>{overallSla}%</span>
        </div>
      )}

      {/* Band counts */}
      <div className="flex items-center gap-2 text-slate-500 border-l border-[#1e3354] pl-4">
        {bandCounts.SEVERE   > 0 && <span className="text-red-400 font-semibold">🔴 {bandCounts.SEVERE} SEVERE</span>}
        {bandCounts.CRITICAL > 0 && <span className="text-orange-400 font-semibold">🟠 {bandCounts.CRITICAL} CRITICAL</span>}
        {bandCounts.WARNING  > 0 && <span className="text-amber-400">🟡 {bandCounts.WARNING} WARNING</span>}
        {bandCounts.HEALTHY  > 0 && <span className="text-green-400">🟢 {bandCounts.HEALTHY} HEALTHY</span>}
        {bandCounts.EXCELLENT > 0 && <span className="text-emerald-400">✅ {bandCounts.EXCELLENT} EXCELLENT</span>}
        {breachedTotal > 0 && <span className="text-red-400 border-l border-[#1e3354] pl-2">⚠ {breachedTotal} breached</span>}
        {leverTotal    > 0 && <span className="text-orange-400">⚡ {leverTotal} levers</span>}
      </div>

      {/* Region dots */}
      <div className="flex items-center gap-1.5 ml-auto">
        {regionDots.map(d => (
          <span key={d.tag} title={`${d.tag.toUpperCase()}: ${d.label}`}
            className={`w-2.5 h-2.5 rounded-full ${d.color} cursor-default`} />
        ))}
        <span className="text-slate-600 ml-1">{total} regions</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [status,      setStatus]  = useState({ state: 'stopped', mode: 'full', last_checked: null })
  const [liveState,   setLive]    = useState(null)
  const [selectedMode, setMode]   = useState('full')
  const [loading,     setLoading] = useState('')
  const [lastUpdate,  setUpdate]  = useState(null)
  const [configRegions,  setConfigRegions]  = useState([])
  const [skillRegionMap, setSkillRegionMap] = useState({})

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/status')
      const d = await r.json()
      setStatus(d)
      setMode(d.mode || 'full')
    } catch {}
  }, [])

  const fetchLive = useCallback(async () => {
    try {
      const r = await fetch('/api/live')
      const d = await r.json()
      setLive(d)
      setUpdate(new Date())
    } catch {}
  }, [])

  useEffect(() => {
    fetchStatus()
    fetchLive()
    fetch('/api/regions').then(r => r.json()).then(d => setConfigRegions(d.regions || [])).catch(() => {})
    fetch('/api/skills').then(r => r.json()).then(d => setSkillRegionMap(d.region_map || {})).catch(() => {})

    socket.on('live_update', data => { setLive(data); setUpdate(new Date()) })
    socket.on('status_update', data => setStatus(data))
    const iv = setInterval(fetchStatus, 5000)
    return () => { socket.off('live_update'); socket.off('status_update'); clearInterval(iv) }
  }, [fetchStatus, fetchLive])

  const doAction = async (action) => {
    setLoading(action)
    try {
      const body = action === 'start' ? { mode: selectedMode } : {}
      await fetch(`/api/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      await new Promise(r => setTimeout(r, 1000))
      await fetchStatus()
    } finally { setLoading('') }
  }

  const isRunning = status.state === 'running'
  const modeLabel = status.mode === 'scrape' ? 'Scrape Only' : 'Scrape & Monitor'

  // Find config region — config stores name as "RTA", "CN" etc., compare case-insensitively
  const getConfigRegion = (tag) =>
    configRegions.find(r => r.name?.toLowerCase() === tag.toLowerCase()) || null

  // Count skills for this region from SKILL_REGION_MAP
  const getConfigSkillCount = (tag) => {
    const apjKey = TAG_TO_APJ[tag]
    return Object.values(skillRegionMap).filter(v => v === apjKey).length
  }

  return (
    <div className="p-6 space-y-6 min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Real-time contact centre SLA monitoring</p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <div className="text-xs text-slate-600">Updated {lastUpdate.toLocaleTimeString()}</div>
          )}
          <a
            href="/portal/cms"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#111827] border border-[#1e3354] text-slate-300 hover:text-white hover:border-blue-500/40 text-sm transition-all"
          >
            <Monitor size={14} /> CMS Portal
          </a>
        </div>
      </div>

      {/* System Status Card */}
      <div className="rta-card p-5">
        <div className="flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-3">
            <div className={`relative flex items-center justify-center w-10 h-10 rounded-full ${isRunning ? 'bg-emerald-500/15' : 'bg-slate-700/30'}`}>
              <span className={`w-3 h-3 rounded-full dot-blink ${isRunning ? 'bg-emerald-400' : 'bg-slate-500'}`} />
            </div>
            <div>
              <div className={`text-sm font-bold ${isRunning ? 'text-emerald-400' : 'text-slate-400'}`}>
                {isRunning ? 'RUNNING' : 'STOPPED'}
              </div>
              {isRunning && <div className="text-xs text-slate-500">{modeLabel}</div>}
              {status.last_checked && <div className="text-xs text-slate-600">Last: {status.last_checked}</div>}
            </div>
          </div>

          <div className="flex items-center gap-4 px-4 border-l border-[#1e3354]">
            <span className="text-xs text-slate-500 font-medium uppercase tracking-wider">Mode</span>
            {[
              { val: 'full',   label: '📊 Scrape & Monitor', sub: 'alerts + levers' },
              { val: 'scrape', label: '🔍 Scrape Only',       sub: 'data collection' },
            ].map(opt => (
              <label key={opt.val} className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="radio" name="mode" value={opt.val}
                  checked={selectedMode === opt.val}
                  onChange={() => setMode(opt.val)}
                  className="accent-blue-500"
                />
                <div>
                  <div className="text-sm text-slate-300 group-hover:text-white transition-colors">{opt.label}</div>
                  <div className="text-xs text-slate-600">{opt.sub}</div>
                </div>
              </label>
            ))}
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <button onClick={() => doAction('start')} disabled={isRunning || !!loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-all">
              <Play size={14} fill="currentColor" />
              {loading === 'start' ? 'Starting…' : 'Start'}
            </button>
            <button onClick={() => doAction('stop')} disabled={!isRunning || !!loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-all">
              <Square size={14} fill="currentColor" />
              {loading === 'stop' ? 'Stopping…' : 'Stop'}
            </button>
            <button onClick={() => doAction('restart')} disabled={!!loading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-all">
              <RotateCcw size={14} />
              {loading === 'restart' ? 'Restarting…' : 'Restart'}
            </button>
          </div>
        </div>
      </div>

      {/* Health Summary Bar */}
      <HealthSummaryBar
        liveState={liveState}
        isRunning={isRunning}
        configRegions={configRegions}
        skillRegionMap={skillRegionMap}
      />

      {/* Region cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Regions — Live Overview</h2>
          <div className="flex items-center gap-3 text-[10px] text-slate-600">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Active</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-slate-600 inline-block" /> Inactive</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> Live</span>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {REGIONS.map(r => (
            <RegionCard
              key={r.tag}
              region={r}
              liveState={liveState}
              isRunning={isRunning}
              configRegion={getConfigRegion(r.tag)}
              configSkillCount={getConfigSkillCount(r.tag)}
              portalUrl={r.portalUrl}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
