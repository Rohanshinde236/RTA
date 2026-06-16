import { useEffect, useState } from 'react'
import { Save, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react'

const REGION_INFO = {
  'APJ-IN':  { name: 'India',     flag: '🇮🇳', accent: 'border-blue-500/40',   badge: 'bg-blue-500/10   text-blue-400   border-blue-500/30'   },
  'APJ-CN':  { name: 'China',     flag: '🇨🇳', accent: 'border-red-500/40',    badge: 'bg-red-500/10    text-red-400    border-red-500/30'    },
  'APJ-AU':  { name: 'Australia', flag: '🇦🇺', accent: 'border-green-500/40',  badge: 'bg-green-500/10  text-green-400  border-green-500/30'  },
  'EMEA':    { name: 'EMEA',      flag: '🌍',  accent: 'border-purple-500/40', badge: 'bg-purple-500/10 text-purple-400 border-purple-500/30' },
  'APJ-HK':  { name: 'Hong Kong', flag: '🇭🇰', accent: 'border-cyan-500/40',   badge: 'bg-cyan-500/10   text-cyan-400   border-cyan-500/30'   },
  'APJ-MY':  { name: 'Malaysia',  flag: '🇲🇾', accent: 'border-teal-500/40',   badge: 'bg-teal-500/10   text-teal-400   border-teal-500/30'   },
  'APJ-KR':  { name: 'Korea',     flag: '🇰🇷', accent: 'border-rose-500/40',   badge: 'bg-rose-500/10   text-rose-400   border-rose-500/30'   },
  'APJ-TH':  { name: 'Thailand',  flag: '🇹🇭', accent: 'border-yellow-500/40', badge: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30' },
  'LATAM-BR':{ name: 'Brazil',    flag: '🇧🇷', accent: 'border-lime-500/40',   badge: 'bg-lime-500/10   text-lime-400   border-lime-500/30'   },
  'APJ-TW':  { name: 'Taiwan',    flag: '🇹🇼', accent: 'border-sky-500/40',    badge: 'bg-sky-500/10    text-sky-400    border-sky-500/30'    },
}
const REGION_ORDER = ['APJ-IN', 'APJ-CN', 'APJ-AU', 'EMEA', 'APJ-HK', 'APJ-MY', 'APJ-KR', 'APJ-TH', 'LATAM-BR', 'APJ-TW']

export default function SkillThresholds() {
  const [skills,    setSkills]   = useState({})
  const [regionMap, setRegionMap]= useState({})
  const [saving,    setSaving]   = useState(false)
  const [saved,     setSaved]    = useState(false)
  const [error,     setError]    = useState('')
  const [expanded,  setExpanded] = useState({ 'APJ-IN': true }) // first region open by default

  useEffect(() => {
    fetch('/api/skills')
      .then(r => r.json())
      .then(d => {
        setSkills(d.skills || {})
        setRegionMap(d.region_map || {})
      })
      .catch(() => {})
  }, [])

  const update = (skill, field, val) =>
    setSkills(s => ({ ...s, [skill]: { ...s[skill], [field]: val } }))

  const save = async () => {
    setSaving(true); setError('')
    try {
      const r = await fetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skills }),
      })
      if (r.ok) { setSaved(true); setTimeout(() => setSaved(false), 3000) }
      else { setError('Save failed') }
    } catch (e) { setError(String(e)) }
    finally { setSaving(false) }
  }

  const toggleRegion = (rk) =>
    setExpanded(s => ({ ...s, [rk]: !s[rk] }))

  // Group skills by region key
  const grouped = {}
  REGION_ORDER.forEach(rk => { grouped[rk] = [] })
  Object.entries(skills).forEach(([skill, cfg]) => {
    const rk = regionMap[skill]
    if (rk && grouped[rk] !== undefined) grouped[rk].push({ skill, cfg })
  })

  return (
    <div className="p-6 min-h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold text-white">📋 Skill Thresholds</h1>
          <p className="text-sm text-slate-500 mt-0.5">Configure per-skill AHT and OCW thresholds — grouped by region</p>
        </div>
        <div className="flex items-center gap-3">
          {saved && <span className="flex items-center gap-1.5 text-emerald-400 text-sm"><CheckCircle size={14}/> Saved — restart to apply</span>}
          {error && <span className="text-red-400 text-sm">{error}</span>}
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-xl btn-save text-white text-sm font-semibold">
            <Save size={14}/> {saving ? 'Saving…' : '💾 Save Skill Thresholds'}
          </button>
        </div>
      </div>

      {/* Region accordion cards */}
      <div className="space-y-3">
        {REGION_ORDER.map(rk => {
          const info   = REGION_INFO[rk]
          const list   = grouped[rk] || []
          const isOpen = !!expanded[rk]
          const activeCount = list.filter(({ cfg }) => cfg.active !== false).length

          return (
            <div key={rk} className={`rta-card overflow-hidden border-l-2 ${info.accent}`}>

              {/* Region card header — click to expand/collapse */}
              <button
                onClick={() => toggleRegion(rk)}
                className="w-full flex items-center justify-between px-5 py-4 hover:bg-[#162540]/40 transition-colors text-left"
              >
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{info.flag}</span>
                  <div>
                    <div className="font-semibold text-white">{info.name}</div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      {list.length} skill{list.length !== 1 ? 's' : ''} · {activeCount} active
                    </div>
                  </div>
                  <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ml-1 ${info.badge}`}>
                    {rk}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-slate-500">
                  <span className="text-xs">{isOpen ? 'Collapse' : 'Expand'}</span>
                  {isOpen
                    ? <ChevronDown size={16} />
                    : <ChevronRight size={16} />
                  }
                </div>
              </button>

              {/* Expanded skill table */}
              {isOpen && list.length > 0 && (
                <div className="border-t border-[#1e3354]">
                  <table className="w-full">
                    <thead>
                      <tr className="bg-[#0d1526]">
                        <th className="px-5 py-2.5 text-xs font-semibold text-slate-500 uppercase text-left">Skill Name</th>
                        <th className="px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase text-center w-48">AHT Target (min)</th>
                        <th className="px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase text-center w-48">OCW Threshold (sec)</th>
                        <th className="px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase text-center w-24">Active</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map(({ skill, cfg }) => (
                        <tr key={skill} className="border-t border-[#1a2a40] hover:bg-[#162540]/30 transition-colors">
                          <td className="px-5 py-3 font-semibold text-slate-200 text-sm">{skill}</td>
                          <td className="px-4 py-3 text-center">
                            <input
                              type="number"
                              value={cfg.aht_target_min ?? 24}
                              onChange={e => update(skill, 'aht_target_min', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#080d1a] border border-[#1e3354] rounded px-2 py-1.5 text-sm text-slate-200 text-center focus:outline-none focus:border-blue-500/60 transition-colors"
                            />
                          </td>
                          <td className="px-4 py-3 text-center">
                            <input
                              type="number"
                              value={cfg.ocw_threshold_sec ?? 60}
                              onChange={e => update(skill, 'ocw_threshold_sec', parseInt(e.target.value) || 0)}
                              className="w-20 bg-[#080d1a] border border-[#1e3354] rounded px-2 py-1.5 text-sm text-slate-200 text-center focus:outline-none focus:border-blue-500/60 transition-colors"
                            />
                          </td>
                          <td className="px-4 py-3 text-center">
                            <input
                              type="checkbox"
                              checked={cfg.active !== false}
                              onChange={e => update(skill, 'active', e.target.checked)}
                              className="w-4 h-4 accent-blue-500 cursor-pointer"
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {isOpen && list.length === 0 && (
                <div className="border-t border-[#1e3354] px-5 py-6 text-center text-slate-600 text-sm italic">
                  No skills configured for this region
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Bottom save */}
      <div className="flex gap-3 mt-5">
        <button onClick={save} disabled={saving}
          className="flex items-center gap-2 px-5 py-2 rounded-xl btn-save text-white text-sm font-semibold">
          <Save size={14}/> {saving ? 'Saving…' : '💾 Save Skill Thresholds'}
        </button>
        <button
          onClick={() => fetch('/api/skills').then(r => r.json()).then(d => { setSkills(d.skills || {}); setRegionMap(d.region_map || {}) })}
          className="px-5 py-2 rounded-lg border border-[#1e3354] text-slate-400 hover:text-slate-200 text-sm transition-colors">
          Cancel
        </button>
      </div>
      <p className="text-xs text-slate-600 mt-2">Changes take effect after system restart.</p>
    </div>
  )
}
