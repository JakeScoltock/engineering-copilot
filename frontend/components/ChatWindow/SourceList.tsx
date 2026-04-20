import type { SourceRef } from '../../types/api'

interface Props {
  sources: SourceRef[]
}

export function SourceList({ sources }: Props) {
  if (sources.length === 0) return null

  return (
    <div className="source-list">
      <span className="source-label">Sources</span>
      <ul className="source-items">
        {sources.map((s, i) => (
          <li key={i} className="source-item" title={`chunk ${s.chunk_index}`}>
            {s.file}
          </li>
        ))}
      </ul>
    </div>
  )
}
