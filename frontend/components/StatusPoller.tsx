'use client'

import { useCallback } from 'react'
import { useRepoStatus } from '../hooks/useRepoStatus'

interface Props {
  repoId: string
  onReady: () => void
}

export function StatusPoller({ repoId, onReady }: Props) {
  const stableOnReady = useCallback(onReady, [onReady])
  const { status, error } = useRepoStatus(repoId, stableOnReady)

  if (error) {
    return (
      <div className="status-container">
        <p className="status-error">Ingestion failed: {error}</p>
      </div>
    )
  }

  return (
    <div className="status-container">
      <div className="spinner" />
      <p className="status-text">
        {status === 'pending' || status === null
          ? 'Fetching and indexing repository…'
          : `Status: ${status}`}
      </p>
      <p className="status-hint">This typically takes 30–90 seconds for small repos.</p>
    </div>
  )
}
