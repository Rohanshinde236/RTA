import { useEffect, useState } from 'react'
import { Save, CheckCircle } from 'lucide-react'

function SectionTitle({ children }) {
  return (
    <div className="text-sm font-bold text-blue-400 border-b-2 border-blue-500/30 pb-2 mt-6 mb-4">
      {children}
    </div>
  )
}

function Field({ label, children, hint }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-600">{hint}</p>}
    </div>
  )
}

function Input({ value, onChange, type = 'text', step, placeholder }) {
  return (
    <input type={type} step={step} value={value ?? ''} onChange={onChange} placeholder={placeholder}
      className="w-full bg-[#080d1a] border border-[#1e3354] rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-blue-500/60 transition-colors"
    />
  )
}

function Select({ value, onChange, options }) {
  return (
    <select value={value ?? ''} onChange={onChange}
      className="w-full bg-[#080d1a] border border-[#1e3354] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-blue-500/60 transition-colors">
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

const AUX_CODES = [
  { code: 'AUX1', name: 'IT Issue'    },
  { code: 'AUX2', name: 'Break'       },
  { code: 'AUX3', name: 'Lunch'       },
  { code: 'AUX4', name: 'Meeting'     },
  { code: 'AUX5', name: 'Training'    },
  { code: 'AUX6', name: 'Case Mgmt'   },
  { code: 'AUX7', name: 'Project'     },
  { code: 'AUX8', name: 'Alt Channel' },
  { code: 'AUX9', name: 'Outbound'    },
]

export default function AgentSettings() {
  const [a1, setA1] = useState({})
  const [a2, setA2] = useState({})
  const [a3, setA3] = useState({})
  const [a4, setA4] = useState({})
  const [saving, setSaving] = useState(false)
  const [saved,  setSaved]  = useState(false)
  const [error,  setError]  = useState('')

  useEffect(() => {
    fetch('/api/agents').then(r => r.json()).then(d => {
      setA1(d.agent1 || {})
      setA2(d.agent2 || {})
      setA3(d.agent3 || {})
      setA4(d.agent4 || {})
    }).catch(() => {})
  }, [])

  const upA1 = (k, v) => setA1(s => ({ ...s, [k]: v }))
  const upA2 = (k, v) => setA2(s => ({ ...s, [k]: v }))
  const upA3 = (k, v) => setA3(s => ({ ...s, [k]: v }))
  const upA4 = (k, v) => setA4(s => ({ ...s, [k]: v }))

  const upAux = (code, field, val) => {
    setA4(s => ({
      ...s,
      aux_thresholds: {
        ...(s.aux_thresholds || {}),
        [code]: { ...(s.aux_thresholds?.[code] || {}), [field]: val }
      }
    }))
  }

  const save = async () => {
    setSaving(true); setError('')
    const emailList = typeof a3.email_recipients === 'string'
      ? a3.email_recipients.split(',').map(e => e.trim()).filter(Boolean)
      : a3.email_recipients || []

    try {
      const r = await fetch('/api/agents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent1: { ...a1, scrape_interval_sec: Number(a1.scrape_interval_sec) },
          agent2: { ...a2, ocw_threshold_sec: Number(a2.ocw_threshold_sec), queue_min: Number(a2.queue_min), cooldown_sec: Number(a2.cooldown_sec) },
          agent3: { ...a3, amber_threshold: Number(a3.amber_threshold), red_threshold: Number(a3.red_threshold), black_threshold: Number(a3.black_threshold), email_recipients: emailList },
          agent4: { ...a4, scrape_interval_sec: Number(a4.scrape_interval_sec), aht_target_min: Number(a4.aht_target_min), acw_target_min: Number(a4.acw_target_min) },
        }),
      })
      if (r.ok) { setSaved(true); setTimeout(() => setSaved(false), 3000) }
      else { setError('Save failed') }
    } catch (e) { setError(String(e)) }
    finally { setSaving(false) }
  }

  const auxThresholds = a4.aux_thresholds || {}

  return (
    <div className="p-6 min-h-full">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-2xl font-bold text-white">⚙️ Agent Settings</h1>
          <p className="text-sm text-slate-500 mt-0.5">Configure all 4 agents and AUX thresholds</p>
        </div>
        <div className="flex items-center gap-3">
          {saved  && <span className="flex items-center gap-1.5 text-emerald-400 text-sm"><CheckCircle size={14}/> Saved — restart to apply</span>}
          {error  && <span className="text-red-400 text-sm">{error}</span>}
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-xl btn-save text-white text-sm font-semibold">
            <Save size={14}/> {saving ? 'Saving…' : '💾 Save Agent Settings'}
          </button>
        </div>
      </div>

      <div className="rta-card p-5">

        {/* Agent 1 */}
        <SectionTitle>Agent 1 — Dashboard Scraper</SectionTitle>
        <div className="grid grid-cols-3 gap-4">
          <Field label="Scraping Interval (seconds)">
            <Input type="number" value={a1.scrape_interval_sec ?? 60} onChange={e => upA1('scrape_interval_sec', e.target.value)} />
          </Field>
          <Field label="Band Drop Email">
            <Select value={a1.band_drop_email_enabled === false ? 'false' : 'true'} onChange={e => upA1('band_drop_email_enabled', e.target.value === 'true')}
              options={[{ value: 'true', label: 'Enabled' }, { value: 'false', label: 'Disabled' }]} />
          </Field>
          <Field label="Band Drop Teams Alert">
            <Select value={a1.band_drop_teams_enabled === false ? 'false' : 'true'} onChange={e => upA1('band_drop_teams_enabled', e.target.value === 'true')}
              options={[{ value: 'true', label: 'Enabled' }, { value: 'false', label: 'Disabled' }]} />
          </Field>
        </div>

        {/* Agent 2 */}
        <SectionTitle>Agent 2 — CMS Analyst + LLM</SectionTitle>
        <div className="grid grid-cols-4 gap-4">
          <Field label="OCW Threshold (seconds)">
            <Input type="number" value={a2.ocw_threshold_sec ?? 60} onChange={e => upA2('ocw_threshold_sec', e.target.value)} />
          </Field>
          <Field label="Queue Minimum (calls)">
            <Input type="number" value={a2.queue_min ?? 1} onChange={e => upA2('queue_min', e.target.value)} />
          </Field>
          <Field label="Cooldown (seconds)">
            <Input type="number" value={a2.cooldown_sec ?? 300} onChange={e => upA2('cooldown_sec', e.target.value)} />
          </Field>
          <Field label="LLM Enabled">
            <Select value={a2.llm_enabled === false ? 'false' : 'true'} onChange={e => upA2('llm_enabled', e.target.value === 'true')}
              options={[{ value: 'true', label: 'Enabled' }, { value: 'false', label: 'Disabled (rule-based)' }]} />
          </Field>
        </div>

        {/* Agent 3 */}
        <SectionTitle>Agent 3 — Lever Generator</SectionTitle>
        <div className="grid grid-cols-4 gap-4 mb-4">
          <Field label="Amber Lever (%)">
            <Input type="number" step="0.1" value={a3.amber_threshold ?? 90.0} onChange={e => upA3('amber_threshold', e.target.value)} />
          </Field>
          <Field label="Red Lever (%)">
            <Input type="number" step="0.1" value={a3.red_threshold ?? 80.0} onChange={e => upA3('red_threshold', e.target.value)} />
          </Field>
          <Field label="Black Lever (%)">
            <Input type="number" step="0.1" value={a3.black_threshold ?? 70.0} onChange={e => upA3('black_threshold', e.target.value)} />
          </Field>
          <Field label="Excel Path">
            <Input value={a3.excel_path ?? ''} onChange={e => upA3('excel_path', e.target.value)} placeholder="Voice_Queue_Intraday.xlsx" />
          </Field>
        </div>
        <Field label="Email Recipients (comma separated)">
          <Input
            value={Array.isArray(a3.email_recipients) ? a3.email_recipients.join(', ') : (a3.email_recipients ?? '')}
            onChange={e => upA3('email_recipients', e.target.value)}
            placeholder="user@company.com, user2@company.com"
          />
        </Field>

        {/* Agent 4 */}
        <SectionTitle>Agent 4 — CMS Monitor</SectionTitle>
        <div className="grid grid-cols-3 gap-4 mb-6">
          <Field label="Scraping Interval (seconds)">
            <Input type="number" value={a4.scrape_interval_sec ?? 60} onChange={e => upA4('scrape_interval_sec', e.target.value)} />
          </Field>
          <Field label="Avg AHT Target (minutes)">
            <Input type="number" value={a4.aht_target_min ?? 1} onChange={e => upA4('aht_target_min', e.target.value)} />
          </Field>
          <Field label="Avg ACW Target (minutes)">
            <Input type="number" value={a4.acw_target_min ?? 1} onChange={e => upA4('acw_target_min', e.target.value)} />
          </Field>
        </div>

        {/* AUX Thresholds */}
        <SectionTitle>Agent 4 — AUX Thresholds</SectionTitle>
        <p className="text-xs text-slate-500 mb-3">Set max time per AUX code. Alert fires if agent exceeds this time. Set 0 to disable monitoring for that AUX.</p>
        <div className="overflow-x-auto rounded-lg border border-[#1e3354]">
          <table className="w-full">
            <thead>
              <tr className="bg-[#0d1526] border-b border-[#1e3354]">
                <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase text-left">AUX Code</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase text-left">Name</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase text-center w-40">Max Time (min)</th>
                <th className="px-4 py-3 text-xs font-semibold text-slate-500 uppercase text-center w-28">Monitor</th>
              </tr>
            </thead>
            <tbody>
              {AUX_CODES.map(({ code, name }) => {
                const cfg = auxThresholds[code] || {}
                return (
                  <tr key={code} className="border-b border-[#1a2a40] hover:bg-[#162540]/40 transition-colors">
                    <td className="px-4 py-3 font-bold text-blue-400 text-sm">{code}</td>
                    <td className="px-4 py-3 text-slate-300 text-sm">{cfg.name || name}</td>
                    <td className="px-4 py-3 text-center">
                      <input type="number" min="0" max="480"
                        value={cfg.max_time_min ?? 0}
                        onChange={e => upAux(code, 'max_time_min', Number(e.target.value))}
                        className="w-24 bg-[#080d1a] border border-[#1e3354] rounded px-2 py-1.5 text-sm text-slate-200 text-center focus:outline-none focus:border-blue-500/60"
                      />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button onClick={() => upAux(code, 'enabled', !cfg.enabled)}
                        className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${cfg.enabled ? 'bg-blue-600' : 'bg-slate-700'}`}>
                        <span className={`inline-block w-4 h-4 bg-white rounded-full shadow transform transition-transform mt-0.5 ${cfg.enabled ? 'translate-x-4' : 'translate-x-0.5'}`}/>
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {/* Save */}
        <div className="flex gap-3 mt-6">
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-5 py-2 rounded-xl btn-save text-white text-sm font-semibold">
            <Save size={14}/> {saving ? 'Saving…' : '💾 Save Agent Settings'}
          </button>
          <button onClick={() => fetch('/api/agents').then(r=>r.json()).then(d=>{ setA1(d.agent1||{}); setA2(d.agent2||{}); setA3(d.agent3||{}); setA4(d.agent4||{}) })}
            className="px-5 py-2 rounded-lg border border-[#1e3354] text-slate-400 hover:text-slate-200 text-sm transition-colors">
            Cancel
          </button>
        </div>
        <p className="text-xs text-slate-600 mt-2">Changes take effect after system restart.</p>
      </div>
    </div>
  )
}
