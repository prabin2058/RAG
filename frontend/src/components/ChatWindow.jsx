// Main chat panel: history, input, thinking indicator, auto-scroll.
//
// Optimistic updates use the TanStack Query v5 pattern:
//   setQueryData() to insert the user's message immediately,
//   invalidateQueries() to replace with server truth on settle.
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { FileQuestion, Loader2, SendHorizonal } from 'lucide-react'
import { getConversationHistory, sendQuery } from '../api.js'
import { useAppStore } from '../store.js'
import MessageBubble from './MessageBubble.jsx'

function historyKey(docId) {
  return ['conversations', docId]
}

export default function ChatWindow() {
  const activeDocId = useAppStore((s) => s.activeDocId)
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const scrollRef = useRef(null)
  const queryClient = useQueryClient()

  // Flatten conversation history into a single message list.
  const { data, isLoading } = useQuery({
    queryKey: historyKey(activeDocId),
    queryFn: () => getConversationHistory(activeDocId),
    enabled: !!activeDocId,
  })

  const messages =
    data?.conversations?.flatMap((conv) =>
      conv.messages.map((m) => ({ ...m, conversationId: conv.id, sources: null })),
    ) ?? []

  // Reset conversation thread when switching documents.
  useEffect(() => {
    setConversationId(null)
    setInput('')
  }, [activeDocId])

  // Auto-scroll to the newest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, thinking])

  const handleSend = async (e) => {
    e.preventDefault()
    const question = input.trim()
    if (!question || thinking) return

    setInput('')
    setThinking(true)

    // Optimistically insert the user message into the cache.
    const optimistic = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: question,
      sources: null,
      created_at: new Date().toISOString(),
    }
    queryClient.setQueryData(historyKey(activeDocId), (old) => {
      const convs = old?.conversations ?? []
      const target = convs.find((c) => c.id === conversationId)
      if (target) {
        return {
          ...old,
          conversations: convs.map((c) =>
            c.id === conversationId ? { ...c, messages: [...c.messages, optimistic] } : c,
          ),
        }
      }
      return {
        doc_id: activeDocId,
        conversations: [
          ...convs,
          { id: conversationId || 'pending', created_at: new Date().toISOString(), messages: [optimistic] },
        ],
      }
    })

    try {
      const res = await sendQuery(activeDocId, question, conversationId)
      setConversationId(res.conversation_id)
      // Refetch replaces the optimistic cache with server truth.
      queryClient.invalidateQueries({ queryKey: historyKey(activeDocId) })
    } catch (err) {
      toast.error(err.message)
      // Roll back the optimistic message on failure.
      queryClient.invalidateQueries({ queryKey: historyKey(activeDocId) })
    } finally {
      setThinking(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
        {!activeDocId && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <FileQuestion size={40} className="text-zinc-700" />
            <p className="text-zinc-500">Select or upload a document to start asking questions</p>
          </div>
        )}

        {activeDocId && isLoading && (
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="flex justify-start">
                <div className="h-14 w-2/3 animate-pulse rounded-2xl bg-zinc-800/60" />
              </div>
            ))}
          </div>
        )}

        {activeDocId && !isLoading && messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="text-zinc-300">Document ready — ask away!</p>
            <p className="text-sm text-zinc-500">
              Questions are answered from the PDF content with page citations.
            </p>
          </div>
        )}

        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.map((m, i) => (
            <MessageBubble key={m.id ?? `idx-${i}`} message={m} />
          ))}

          {thinking && (
            <div className="flex items-center gap-2 text-sm text-zinc-400">
              <Loader2 size={16} className="animate-spin text-indigo-400" />
              <span className="animate-pulse">Thinking…</span>
            </div>
          )}
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-zinc-800 px-4 py-4 md:px-8">
        <form
          onSubmit={handleSend}
          className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 p-2 focus-within:border-indigo-500"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend(e)
              }
            }}
            disabled={!activeDocId || thinking}
            rows={1}
            placeholder={activeDocId ? 'Ask a question about this document…' : 'Select a document first'}
            className="max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-zinc-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!activeDocId || thinking || !input.trim()}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40"
            aria-label="Send"
          >
            <SendHorizonal size={16} />
          </button>
        </form>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-zinc-600">
          Answers are generated locally by Ollama using only the content of the selected PDF.
        </p>
      </div>
    </div>
  )
}