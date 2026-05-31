import { useState } from 'react'
import { hasTokens } from './api/client'
import LoginPage from './pages/LoginPage'
import ScannerPage from './pages/ScannerPage'

export default function App() {
  const [authed, setAuthed] = useState<boolean>(hasTokens)

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {authed ? (
        <ScannerPage onLogout={() => setAuthed(false)} />
      ) : (
        <LoginPage onLogin={() => setAuthed(true)} />
      )}
    </div>
  )
}
