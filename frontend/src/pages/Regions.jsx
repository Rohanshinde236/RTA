import { useEffect, useState } from 'react'
import { Save, CheckCircle, ExternalLink, Trash2, ToggleLeft, ToggleRight } from 'lucide-react'

const EMPTY_REGION = { name: '', display: '', dashboard: '', webhook: '', active: true }

export default function Regions() {
  const [regions, setRegions] = useState([])
  const [saving, setSaving]   = useState(false)
  const [saved,  setSaved]    = useState(false)
  const [error,  setError]    = useState('')

  useEffect(() => {
    fetch('/api/regions').then(r => r.json()).then(d => setRegions(d.regions || [])).catch(() => {})
  }, [])

  const update = (i, field, val) => setRegions(rs => rs.map((r, idx) => idx === i ? { ...r, [field]: val } : r))
  const remove = (i) => setRegions(rs => rs.filter((_, idx) => idx !== i))
  const add    = () => setRegions(rs => [...rs, { ...EMPTY_REGION }])

  const save = async () => {
    setSaving(true); setError('')
    try {
      const r = await fetch('/api/regions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ regions }),
      })
      if (r.ok) { setSaved(true); setTimeout(() => setSaved(false), 3000) }
      else { setError('Save failed') }
    } catch (e) { setError(String(e)) }
    finally { setSaving(false) }
  }

  return (
    <div className="p-6 space-y-5 min-h-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">🌍 Regions</h1>
          <p className="text-sm text-slate-500 mt-0.5">Configure region names, dashboards, and Teams webhooks</p>
        </div>
        <div className="flex items-center gap-3">
          {saved  && <span className="flex items-center gap-1.5 text-emerald-400 text-sm"><CheckCircle size={14}/> Saved — restart to apply</span>}
          {error  && <span className="text-red-400 text-sm">{error}</span>}
          <button onClick={add}
            className="px-3 py-2 rounded-lg bg-[#111827] border border-[#1e3354] text-slate-300 hover:text-white text-sm transition-colors">
            + Add Region
          </button>
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium">
            <Save size={14}/> {saving ? 'Saving…' : '💾 Save Regions'}
          </button>
        </div>
      </div>

      {regions.map((r, i) => (
        <div key={i} className="rta-card overflow-hidden">
          {/* Card header */}
          <div className="flex items-center justify-between px-5 py-3 bg-[#0d1526] border-b border-[#1e3354]">
            <span className="font-semibold text-slate-200">
              Region {i + 1} — {r.display || 'New Region'}
            </span>
            <div className="flex items-center gap-3">
              <button onClick={() => update(i, 'active', !r.active)}
                className={`flex items-center gap-1.5 text-sm font-medium transition-colors ${r.active ? 'text-emerald-400' : 'text-slate-500'}`}>
                {r.active ? <ToggleRight size={20}/> : <ToggleLeft size={20}/>}
                {r.active ? 'Active' : 'Inactive'}
              </button>
              {r.dashboard && (
                <a href={`/dashboard/view/${i}`} target="_blank" rel="noreferrer"
                  className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 border border-blue-500/30 px-2 py-1 rounded transition-colors">
                  <ExternalLink size={11}/> View Dashboard
                </a>
              )}
            </div>
          </div>

          {/* Card body */}
          <div className="p-5">
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Region Name</label>
                <input
                  value={r.name} onChange={e => update(i, 'name', e.target.value)}
                  placeholder="e.g. RTA"
                  className="w-full bg-[#080d1a] border border-[#1e3354] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-blue-500/60 transition-colors"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Display Name</label>
                <input
                  value={r.display} onChange={e => update(i, 'display', e.target.value)}
                  placeholder="e.g. Client ProSupport IND"
                  className="w-full bg-[#080d1a] border border-[#1e3354] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-blue-500/60 transition-colors"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Dashboard File</label>
                <div className="flex gap-2">
                  <input
                    value={r.dashboard} onChange={e => update(i, 'dashboard', e.target.value)}
                    placeholder="ui/RTA.html"
                    className="flex-1 bg-[#080d1a] border border-[#1e3354] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-blue-500/60 transition-colors"
                  />
                  <button onClick={() => remove(i)}
                    className="px-3 py-2 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors text-xs">
                    <Trash2 size={13}/>
                  </button>
                </div>
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Teams Webhook URL</label>
              <input
                value={r.webhook} onChange={e => update(i, 'webhook', e.target.value)}
                placeholder="https://outlook.office.com/webhook/..."
                className="w-full bg-[#080d1a] border border-[#1e3354] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-blue-500/60 transition-colors font-mono text-xs"
              />
            </div>
          </div>
        </div>
      ))}

      {regions.length === 0 && (
        <div className="rta-card flex flex-col items-center justify-center py-16 text-slate-600">
          <p className="text-sm mb-3">No regions configured</p>
          <button onClick={add} className="text-blue-400 text-sm hover:text-blue-300">+ Add Region</button>
        </div>
      )}

      <div className="flex gap-3">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium">
          <Save size={14}/> {saving ? 'Saving…' : '💾 Save Regions'}
        </button>
        <button onClick={() => fetch('/api/regions').then(r=>r.json()).then(d=>setRegions(d.regions||[]))}
          className="px-5 py-2 rounded-lg border border-[#1e3354] text-slate-400 hover:text-slate-200 text-sm transition-colors">
          Cancel
        </button>
      </div>
      <p className="text-xs text-slate-600">Changes take effect after system restart.</p>
    </div>
  )
}
