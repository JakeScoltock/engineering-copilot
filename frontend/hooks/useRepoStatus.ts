'use client'

import { useEffect, useRef, useState } from 'react'
import type { IngestionStatus, RepoResponse } from '../types/api'

export function useRepoStatus(repoId: string | null, onReady: () => void) {
  const [status, setStatus] = useState<IngestionStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Stable ref so the interval callback always calls the latest onReady
  const onReadyRef = useRef(onReady)
  useEffect(() => {
    onReadyRef.current = onReady
  })

  useEffect(() => {
    if (!repoId) return

    let stopped = false

    const poll = async () => {
      try {
        const res = await fetch(`/api/repos/${repoId}`)
        if (stopped) return
        const data: RepoResponse = await res.json()
        setStatus(data.status)
        if (data.status === 'failed') {
          setError(data.error ?? 'Ingestion failed')
          stopped = true
        } else if (data.status === 'ready') {
          stopped = true
          onReadyRef.current()
        }
      } catch {
        // network hiccup — keep polling
      }
    }

    poll()
    const id = setInterval(() => {
      if (!stopped) poll()
    }, 3000)

    return () => {
      stopped = true
      clearInterval(id)
    }
  }, [repoId])

  return { status, error }
}
