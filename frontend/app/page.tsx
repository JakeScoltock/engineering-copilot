'use client'

import { useCallback, useState } from 'react'
import { ChatWindow } from '../components/ChatWindow/ChatWindow'
import { StatusPoller } from '../components/StatusPoller'
import { UrlForm } from '../components/UrlForm'

type AppState =
  | { view: 'input' }
  | { view: 'loading'; repoId: string }
  | { view: 'chat'; repoId: string }

export default function Home() {
  const [state, setState] = useState<AppState>({ view: 'input' })

  const handleRepoSubmit = (repoId: string) => {
    setState({ view: 'loading', repoId })
  }

  const handleReady = useCallback(() => {
    setState(prev => prev.view === 'loading' ? { view: 'chat', repoId: prev.repoId } : prev)
  }, [])

  return (
    <main className="app-main">
      {state.view === 'input' && <UrlForm onSubmit={handleRepoSubmit} />}
      {state.view === 'loading' && (
        <StatusPoller repoId={state.repoId} onReady={handleReady} />
      )}
      {state.view === 'chat' && <ChatWindow repoId={state.repoId} />}
    </main>
  )
}
