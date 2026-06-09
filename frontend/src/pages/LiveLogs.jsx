import { useEffect, useRef, useState } from 'react'
import { socket } from '../socket'
import { Trash2, PauseCircle, PlayCircle, Download } from 'lucide-react'

function colorLine(line) {
  const l = line.toLowerCase()
  if (l.includes('error') || l.includes('exception') || l.includes('traceback') || l.includes('critical'))
    return 'text-red-400'
  if (l.includes('warn') || l.includes('warning'))
    return 'text-amber-400'
  if (l.includes('lever') || l.includes('alert') || l.includes('breach'))
    return 'text-orange-400'
  if (l.includes('success') || l.includes('started') || l.includes('completed') || l.includes('saved'))
    return 'text-emerald-400'
  if (l.includes('agent') || l.includes('[rta]') || l.includes('[cn]') || l.includes('[au]') || l.includes('[emea]'))
    return 'text-blue-400'
  return 'text-slate-400'
}

export default function LiveLogs() {
  const [lines, setLines]     = useState([])
  const [paused, setPaused]   = useState(false)
  const [filter, setFilter]   = useState('')
  const bottomRef = useRef(null)
  const pauseRef  = useRef(false)

  useEffect(() => {
    fetch('/api/logs').then(r => r.json()).then(d => setLines(d.lines || [])).catch(() => {})
    socket.on('log_line', line => {
      if (!pauseRef.current)
        setLines(prev => [...prev.slice(-499), line])
    })
    return () => socket.off('log_line')
  }, [])

  useEffect(() => { pauseRef.current = paused }, [paused])

  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, paused])

  const shown = filter
    ? lines.filter(l => l.toLowerCase().includes(filter.toLowerCase()))
    : lines

  const download = () => {
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `rta_logs_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.txt`
    a.click()
  }

  return (
    <div className="p-6 flex flex-col h-full gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Live Logs</h1>
          <p className="text-sm text-slate-500 mt-0.5">Real-time agent and system activity</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={filter} onChange={e => setFilter(e.target.value)}
            placeholder="Filter logs…"
            className="bg-[#0d1526] border border-[#1e3354] rounded-lg px-3 py-2 text-sm text-slate-300 placeholder-slate-700 focus:outline-none focus:border-blue-500/40 w-48"
          />
          <button onClick={() => setPaused(p => !p)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${paused ? 'bg-amber-600/20 text-amber-400 border border-amber-500/30' : 'bg-[#111827] text-slate-400 border border-[#1e3354] hover:text-slate-200'}`}>
            {paused ? <><PlayCircle size={14} /> Resume</> : <><PauseCircle size={14} /> Pause</>}
          </button>
          <button onClick={download}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-slate-400 border border-[#1e3354] hover:text-slate-200 bg-[#111827] transition-colors">
            <Download size={14} /> Export
          </button>
          <button onClick={() => setLines([])}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-slate-500 border border-[#1e3354] hover:text-red-400 bg-[#111827] transition-colors">
            <Trash2 size={14} /> Clear
          </button>
        </div>
      </div>

      {/* Terminal */}
      <div className="flex-1 min-h-0 rta-card log-terminal overflow-y-auto p-4 rounded-xl">
        {shown.length === 0 ? (
          <div className="text-slate-700 text-center mt-16 text-sm">
            {filter ? 'No lines match filter' : 'No logs yet — start the system'}
          </div>
        ) : (
          shown.map((line, i) => (
            <div key={i} className={`leading-relaxed whitespace-pre-wrap break-all ${colorLine(line)}`}>
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-4 text-xs text-slate-600">
        <span>{shown.length} lines{filter ? ` (filtered from ${lines.length})` : ''}</span>
        {paused && <span className="text-amber-500">● Paused — scroll paused</span>}
        <span className="ml-auto">
          <span className="text-red-500/70">■</span> Error &nbsp;
          <span className="text-amber-500/70">■</span> Warning &nbsp;
          <span className="text-emerald-500/70">■</span> Success &nbsp;
          <span className="text-blue-500/70">■</span> Agent
        </span>
      </div>
    </div>
  )
}
