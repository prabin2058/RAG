// Single chat message: user right-aligned, assistant left-aligned with sources.
import { Bot, User } from 'lucide-react'
import SourceCitation from './SourceCitation.jsx'

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-600/20 text-indigo-400">
          <Bot size={16} />
        </div>
      )}

      <div className={`max-w-[80%] ${isUser ? 'order-first' : ''}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? 'rounded-br-sm bg-indigo-600 text-white'
              : 'rounded-bl-sm border border-zinc-800 bg-zinc-900 text-zinc-100'
          }`}
        >
          {message.content}
        </div>
        {!isUser && <SourceCitation sources={message.sources} />}
      </div>

      {isUser && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-zinc-300">
          <User size={16} />
        </div>
      )}
    </div>
  )
}