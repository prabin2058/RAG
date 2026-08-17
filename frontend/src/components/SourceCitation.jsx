// Collapsible "Sources" section rendered under each assistant message.
import { useState } from 'react'
import { ChevronDown, ChevronRight, FileSearch } from 'lucide-react'

export default function SourceCitation({ sources }) {
  const [open, setOpen] = useState(false)
  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-2 rounded-lg border border-zinc-700/60 bg-zinc-800/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-zinc-300 hover:text-zinc-100"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <FileSearch size={14} className="text-indigo-400" />
        Sources ({sources.length})
      </button>
      {open && (
        <ul className="space-y-2 border-t border-zinc-700/60 px-3 py-2">
          {sources.map((src, i) => (
            <li key={i} className="text-xs leading-relaxed">
              <span className="font-semibold text-indigo-400">Page {src.page_number}</span>
              <p className="mt-0.5 line-clamp-3 text-zinc-400">{src.snippet}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}