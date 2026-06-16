import { useEffect, useState, useCallback } from 'react'
import { Monitor } from 'lucide-react'
import { socket } from '../socket'
import { REGIONS } from '../regions'

function stateColor(state) {
  if (state === 'AUX') return 'text-amber-400 bg-amber-500/15 border-amber-500/30'
  if (state === 'ACD') return 'text-blue-400 bg-blue-500/15 border-blue-500/30'
  if (state === 'ACW') return 'text-purple-400 bg-purple-500/15 border-purple-500/30'
  return 'text-slate-400 bg-slate-700/30 border-slate-600/30'
}

export default function AuxThresholds() {
  const [cmsAgents, setCmsAgents]   = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [isRunning, setRunning]     = useState(false)
  const [showAll, setShowAll]       = useState(false)

  const fetchCms = useCallback(async () => {
    try {
      const r = await fetch('/api/cms_agents')
      setCmsAgents(await r.json())
      setLastUpdate(new Date())
    } catch {}
  }, [])

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/status')
      const d = await r.json()
      setRunning(d.state === 'running')
    } catch {}
  }, [])

  useEffect(() => {
    fetchStatus()
    fetchCms()
    socket.on('status_update', d => setRunning(d.state === 'running'))
    const statusIv = setInterval(fetchStatus, 5000)
    const cmsIv    = setInterval(fetchCms, 60000)
    return () => { socket.off('status_update'); clearInterval(statusIv); clearInterval(cmsIv) }
  }, [fetchStatus, fetchCms])

  const regionRows = REGIONS.map(r => {
    const rd = cmsAgents?.[r.tag]
    if (!rd) return { region: r, agents: [] }
    const agents = []
    Object.entries(rd).forEach(([, list]) => list.forEach(a => agents.push(a)))
    const filtered = showAll
      ? agents.filter(a => a.state !== 'AVAIL')
      : agents.filter(a => a.state === 'AUX')
    return { region: r, agents: filtered.sort((a, b) => b.time_minutes - a.time_minutes) }
  }).filter(r => r.agents.length > 0)

  const totalBreaches = regionRows.flatMap(r => r.agents).filter(a => a.breach).length
  const noData = !cmsAgents || Object.keys(cmsAgents).length === 0

  return (
    <div className="p-6 space-y-6 min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-amber-600/20 border border-amber-500/30 flex items-center justify-center">
            <Monitor size={18} className="text-amber-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">AUX Thresholds</h1>
            <p className="text-sm text-slate-500 mt-0.5">Agent 4 — CMS monitor: agents exceeding AUX / AHT / ACW limits</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {totalBreaches > 0 && (
            <span className="text-xs font-semibold text-red-400 bg-red-500/10 border border-red-500/30 px-2.5 py-1 rounded-full">
              {totalBreaches} exceeded
            </span>
          )}
          {lastUpdate && (
            <span className="text-[10px] text-slate-600">Updated {lastUpdate.toLocaleTimeString()}</span>
          )}
          <button
            onClick={() => setShowAll(v => !v)}
            className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded-lg transition-colors"
          >
            {showAll ? 'AUX only' : 'All states'}
          </button>
        </div>
      </div>

      {!isRunning && (
        <div className="rta-card px-5 py-4 text-sm text-slate-500 italic">
          System is stopped — start it from the Dashboard to see live CMS agent data.
        </div>
      )}

      {isRunning && noData && (
        <div className="rta-card px-5 py-4 text-sm text-slate-500 italic">
          No Agent 4 data yet — CMS monitor polls every 60s.
        </div>
      )}

      {isRunning && !noData && regionRows.length === 0 && (
        <div className="rta-card px-5 py-4 text-sm text-slate-500 italic">
          {showAll ? 'No non-available agents right now.' : 'No agents on AUX right now.'}
        </div>
      )}

      {isRunning && regionRows.map(({ region, agents }) => {
        const regionBreaches = agents.filter(a => a.breach).length
        return (
          <div key={region.tag} className="rta-card overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1e3354]">
              <div className="flex items-center gap-2">
                <span className="text-base">{region.flag}</span>
                <span className="text-sm font-semibold text-white">{region.name}</span>
                <span className="text-xs text-slate-500">{agents.length} agent{agents.length !== 1 ? 's' : ''}</span>
              </div>
              {regionBreaches > 0 && (
                <span className="text-xs text-red-400 font-medium">⚠ {regionBreaches} exceeded</span>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-600 border-b border-[#1a2a44]">
                    <th className="text-left px-4 py-2 font-medium">Skill</th>
                    <th className="text-left px-4 py-2 font-medium">Agent</th>
                    <th className="text-left px-4 py-2 font-medium">State</th>
                    <th className="text-left px-4 py-2 font-medium">Type / Reason</th>
                    <th className="text-right px-4 py-2 font-medium">Time</th>
                    <th className="text-right px-4 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((a, i) => (
                    <tr key={i} className={`border-b border-[#111827] last:border-0 ${a.breach ? 'bg-red-500/5' : ''}`}>
                      <td className="px-4 py-2 text-slate-400 font-mono">{a.skill.replace(/^TS_/, '')}</td>
                      <td className="px-4 py-2 text-white font-medium">{a.name}</td>
                      <td className="px-4 py-2">
                        <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${stateColor(a.state)}`}>{a.state}</span>
                      </td>
                      <td className="px-4 py-2 text-slate-400">
                        {a.state === 'AUX' ? (a.aux_name || a.aux_reason || '—') : '—'}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums text-slate-300">
                        {a.time_minutes > 0 ? `${a.time_minutes.toFixed(1)}m` : '—'}
                      </td>
                      <td className="px-4 py-2 text-right">
                        {a.breach
                          ? <span className="text-red-400 font-semibold">⚠ EXCEEDED</span>
                          : <span className="text-slate-600">OK</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}
    </div>
  )
}
