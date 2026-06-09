import { useEffect, useRef, useState } from 'react'
import { Send, Database, Radio, Trash2, Bot } from 'lucide-react'

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-4 py-3">
      {[0,1,2].map(i => (
        <span key={i} className={`typing-dot w-2 h-2 rounded-full bg-blue-400`} />
      ))}
    </div>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4 animate-slide-in`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center mr-2 mt-1 flex-shrink-0">
          <Bot size={14} className="text-blue-400" />
        </div>
      )}
      <div className={`max-w-[75%] px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${isUser ? 'chat-user text-slate-200' : 'chat-bot text-slate-300'}`}>
        {msg.content}
      </div>
    </div>
  )
}

const SUGGESTIONS = [
  'Which region is performing worst right now?',
  'What was TS_VICHW yesterday?',
  'Who is on AUX in India?',
  'Show me lever fires today',
  'What is the current SLA for China?',
]

export default function Chatbot() {
  const [messages, setMessages] = useState([])
  const [input, setInput]       = useState('')
  const [mode, setMode]         = useState('live')   // 'live' | 'history'
  const [loading, setLoading]   = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  // Restore from sessionStorage
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem('rta_chat')
      if (saved) setMessages(JSON.parse(saved))
    } catch {}
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    try { sessionStorage.setItem('rta_chat', JSON.stringify(messages.slice(-40))) } catch {}
  }, [messages])

  const send = async (text) => {
    const q = (text || input).trim()
    if (!q || loading) return
    setInput('')
    setMessages(m => [...m, { role: 'user', content: q }])
    setLoading(true)
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, mode }),
      })
      const d = await r.json()
      setMessages(m => [...m, { role: 'bot', content: d.answer || d.error || 'No response' }])
    } catch (e) {
      setMessages(m => [...m, { role: 'bot', content: `Error: ${e.message}` }])
    } finally { setLoading(false) }
  }

  const onKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#1e3354] bg-[#0d1526]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center">
            <Bot size={18} className="text-blue-400" />
          </div>
          <div>
            <div className="font-semibold text-white text-sm">RTA Bot</div>
            <div className="text-xs text-slate-500">AI-powered SLA analyst</div>
          </div>
        </div>

        {/* Mode toggle */}
        <div className="flex items-center gap-1 p-1 bg-[#080d1a] rounded-lg border border-[#1e3354]">
          <button
            onClick={() => setMode('live')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all ${mode === 'live' ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : 'text-slate-500 hover:text-slate-300'}`}
          >
            <Radio size={11} /> Live
          </button>
          <button
            onClick={() => setMode('history')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all ${mode === 'history' ? 'bg-purple-600/20 text-purple-400 border border-purple-500/30' : 'text-slate-500 hover:text-slate-300'}`}
          >
            <Database size={11} /> History
          </button>
        </div>

        <button
          onClick={() => { setMessages([]); sessionStorage.removeItem('rta_chat') }}
          className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-400 transition-colors"
        >
          <Trash2 size={12} /> Clear
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 min-h-0">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-6 text-center">
            <div className="w-16 h-16 rounded-2xl bg-blue-600/10 border border-blue-500/20 flex items-center justify-center">
              <Bot size={32} className="text-blue-500/60" />
            </div>
            <div>
              <p className="text-slate-400 font-medium mb-1">Ask me anything about SLA performance</p>
              <p className="text-slate-600 text-sm">
                {mode === 'live' ? 'Using current live dashboard data' : 'Querying 7-day history database'}
              </p>
            </div>
            <div className="grid grid-cols-1 gap-2 w-full max-w-sm">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-xs px-3 py-2 rounded-lg bg-[#111827] border border-[#1e3354] text-slate-400 hover:border-blue-500/40 hover:text-slate-200 transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => <Message key={i} msg={m} />)}
        {loading && (
          <div className="flex justify-start mb-4">
            <div className="w-7 h-7 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center mr-2 mt-1">
              <Bot size={14} className="text-blue-400" />
            </div>
            <div className="chat-bot">
              <TypingDots />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Mode indicator bar */}
      <div className={`px-6 py-1.5 text-xs border-t border-[#1e3354] ${mode === 'history' ? 'text-purple-500 bg-purple-500/5' : 'text-blue-500 bg-blue-500/5'}`}>
        {mode === 'live'
          ? '● Live mode — answering from current dashboard data'
          : '● History mode — querying SQLite database (7-day window)'}
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-[#1e3354] bg-[#0d1526]">
        <div className="flex items-end gap-3">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Ask about SLA, agents, levers, breaches…"
            rows={1}
            className="flex-1 resize-none bg-[#080d1a] border border-[#1e3354] rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-700 focus:outline-none focus:border-blue-500/50 transition-colors leading-relaxed max-h-32"
            style={{ height: 'auto' }}
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading}
            className="w-10 h-10 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-all flex-shrink-0"
          >
            <Send size={15} className="text-white" />
          </button>
        </div>
        <p className="text-[10px] text-slate-700 mt-2">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  )
}
