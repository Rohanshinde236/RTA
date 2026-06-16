import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import Regions from './pages/Regions'
import AgentSettings from './pages/AgentSettings'
import SkillThresholds from './pages/SkillThresholds'
import AuxThresholds from './pages/AuxThresholds'
import LiveLogs from './pages/LiveLogs'
import Chatbot from './pages/Chatbot'

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-[#080d1a] text-slate-100 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto min-h-0">
          <Routes>
            <Route path="/"                element={<Dashboard />} />
            <Route path="/regions"         element={<Regions />} />
            <Route path="/agent-settings"  element={<AgentSettings />} />
            <Route path="/thresholds"      element={<SkillThresholds />} />
            <Route path="/aux-thresholds"  element={<AuxThresholds />} />
            <Route path="/logs"            element={<LiveLogs />} />
            <Route path="/chatbot"         element={<Chatbot />} />
            <Route path="*"               element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
