'use client'

import { useState } from 'react'
import type { Message, StreamEvent } from '../types/api'

export function useStreamingQuery(repoId: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)

  const submit = async (question: string) => {
    if (isStreaming) return

    // Build history from completed messages (last 10 turns)
    const history = messages
      .filter(m => !m.isStreaming)
      .slice(-10)
      .map(m => ({ role: m.role, content: m.content }))

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: question,
    }
    const assistantId = crypto.randomUUID()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)

    try {
      const streamingUrl = process.env.NEXT_PUBLIC_STREAMING_URL
      const apiKey = process.env.NEXT_PUBLIC_STREAMING_API_KEY
      const res = await fetch(`${streamingUrl}/repos/${repoId}/query`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-api-key': apiKey ?? '',
        },
        body: JSON.stringify({ question, history }),
      })

      if (!res.body) throw new Error('No response body')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const event: StreamEvent = JSON.parse(line)
            if (event.type === 'sources') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId ? { ...m, sources: event.sources } : m,
                ),
              )
            } else if (event.type === 'delta') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: m.content + event.text }
                    : m,
                ),
              )
            } else if (event.type === 'done') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: event.answer, isStreaming: false }
                    : m,
                ),
              )
            } else if (event.type === 'error') {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: `Error: ${event.error}`, isStreaming: false }
                    : m,
                ),
              )
            }
          } catch {
            // ignore malformed NDJSON lines
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Request failed'
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, content: `Error: ${msg}`, isStreaming: false }
            : m,
        ),
      )
    } finally {
      setIsStreaming(false)
    }
  }

  return { messages, isStreaming, submit }
}
