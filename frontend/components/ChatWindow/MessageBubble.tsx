import type { Message } from '../../types/api'
import { SourceList } from './SourceList'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
      <div className={`bubble ${isUser ? 'bubble--user' : 'bubble--assistant'}`}>
        <p className="bubble-text">
          {message.content}
          {message.isStreaming && <span className="cursor">▋</span>}
        </p>
        {!isUser && message.sources && <SourceList sources={message.sources} />}
      </div>
    </div>
  )
}
