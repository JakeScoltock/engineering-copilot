export type IngestionStatus = 'pending' | 'ready' | 'failed'

export interface RepoResponse {
  repo_id: string
  status: IngestionStatus
  error?: string | null
}

export interface SourceRef {
  file: string
  chunk_index: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

// NDJSON events emitted by the streaming Lambda
export type StreamEvent =
  | { type: 'sources'; sources: SourceRef[] }
  | { type: 'delta'; text: string }
  | { type: 'done'; answer: string }
  | { type: 'error'; error: string }

// Frontend message with extra UI state
export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: SourceRef[]
  isStreaming?: boolean
}
