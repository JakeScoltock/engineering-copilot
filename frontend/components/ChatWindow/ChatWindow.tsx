'use client'

import { FormEvent, useEffect, useRef, useState } from 'react'
import { useStreamingQuery } from '../../hooks/useStreamingQuery'
import { MessageBubble } from './MessageBubble'

interface Props {
  repoId: string
}

export function ChatWindow({ repoId }: Props) {
  const { messages, isStreaming, submit } = useStreamingQuery(repoId)
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const q = input.trim()
    if (!q || isStreaming) return
    setInput('')
    submit(q)
  }

  return (
    <div className="chat-layout">
      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-empty">Ask anything about the repository.</p>
        )}
        {messages.map(m => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </div>
      <form className="chat-input-form" onSubmit={handleSubmit}>
        <input
          className="chat-input"
          type="text"
          placeholder="Ask a question…"
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={isStreaming}
          autoFocus
        />
        <button
          className="chat-send"
          type="submit"
          disabled={isStreaming || !input.trim()}
        >
          {isStreaming ? '…' : 'Send'}
        </button>
      </form>
    </div>
  )
}
