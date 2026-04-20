'use client'

import { FormEvent, useState } from 'react'

interface Props {
  onSubmit: (repoId: string) => void
}

export function UrlForm({ onSubmit }: Props) {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await fetch('/api/repos', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ github_url: url.trim() }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? 'Failed to submit repository')
        return
      }
      onSubmit(data.repo_id)
    } catch {
      setError('Network error — please try again')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="url-form-container">
      <h1 className="url-form-title">engineering-copilot</h1>
      <p className="url-form-subtitle">Ask questions about any public GitHub repository</p>
      <form onSubmit={handleSubmit} className="url-form">
        <input
          className="url-input"
          type="url"
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={e => setUrl(e.target.value)}
          required
          disabled={loading}
        />
        <button className="url-submit" type="submit" disabled={loading || !url.trim()}>
          {loading ? 'Submitting…' : 'Ingest →'}
        </button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}
