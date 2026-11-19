// Sidebar: document list with status badges, upload button, delete, user menu.
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { FileText, Loader2, LogOut, Trash2, Upload, XCircle } from 'lucide-react'
import { deleteDocument, listDocuments } from '../api.js'
import { useAppStore } from '../store.js'
import { useAuth } from '../AuthContext.jsx'
import UploadModal from './UploadModal.jsx'

const STATUS_BADGE = {
  processing: 'bg-amber-500/15 text-amber-400 animate-pulse',
  ready: 'bg-emerald-500/15 text-emerald-400',
  failed: 'bg-red-500/15 text-red-400',
}

function StatusBadge({ status }) {
  const label = status === 'processing' ? 'Processing' : status === 'ready' ? 'Ready' : 'Failed'
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE[status] || 'bg-zinc-800 text-zinc-400'}`}>
      {status === 'processing' ? <Loader2 size={11} className="animate-spin" /> : null}
      {label}
    </span>
  )
}

function DocumentRow({ doc, active, onSelect, onDelete }) {
  return (
    <div
      className={`group mb-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 transition-colors ${
        active ? 'bg-zinc-800' : 'hover:bg-zinc-900'
      }`}
    >
      <button
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
        title={`Ask questions about ${doc.filename}`}
      >
        <FileText size={18} className="shrink-0 text-zinc-400" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{doc.filename}</p>
          <p className="text-xs text-zinc-500">{doc.num_pages} pages</p>
        </div>
      </button>
      <div className="flex flex-col items-end gap-1.5">
        <StatusBadge status={doc.status} />
        <button
          onClick={onDelete}
          className="hidden rounded p-1 text-zinc-500 hover:bg-red-500/10 hover:text-red-400 group-hover:block"
          title="Delete document"
          aria-label={`Delete ${doc.filename}`}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}

export default function Sidebar({ onDocSelected }) {
  const [uploadOpen, setUploadOpen] = useState(false)
  const queryClient = useQueryClient()
  const { activeDocId, setActiveDocId } = useAppStore()
  const { user, logout } = useAuth()

  const { data: docs, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: listDocuments,
  })

  const handleDelete = async (docId, filename) => {
    if (!window.confirm(`Delete "${filename}"? This removes the document, index, and chat history.`)) return
    try {
      await deleteDocument(docId)
      if (activeDocId === docId) setActiveDocId(null)
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      toast.success('Document deleted')
    } catch (err) {
      toast.error(err.message)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-4">
        <div>
          <h1 className="text-lg font-bold">RAG Document Q&amp;A</h1>
          <p className="text-xs text-zinc-500">Local · Free · No API keys</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="max-w-[110px] truncate rounded-full bg-zinc-800 px-2.5 py-1 text-[11px] text-zinc-400"
            title={user?.email}
          >
            {user?.email}
          </span>
          <button
            onClick={logout}
            className="rounded-lg p-1.5 text-zinc-500 hover:bg-red-500/10 hover:text-red-400"
            title="Log out"
            aria-label="Log out"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>

      <div className="border-b border-zinc-800 px-4 py-3">
        <button
          onClick={() => setUploadOpen(true)}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium hover:bg-indigo-500"
        >
          <Upload size={16} /> Upload
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading && (
          <div className="space-y-2 px-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-lg bg-zinc-800/60" />
            ))}
          </div>
        )}

        {!isLoading && (!docs || docs.length === 0) && (
          <p className="px-4 py-8 text-center text-sm text-zinc-500">
            No documents yet.
            <br />Upload a document to get started.
          </p>
        )}

        {docs?.map((doc) => (
          <DocumentRow
            key={doc.id}
            doc={doc}
            active={activeDocId === doc.id}
            onSelect={() => {
              setActiveDocId(doc.id)
              onDocSelected?.()
            }}
            onDelete={() => handleDelete(doc.id, doc.filename)}
          />
        ))}

        {docs?.some((d) => d.status === 'failed') && (
          <p className="mt-2 flex items-center gap-1 px-3 text-xs text-red-400">
            <XCircle size={12} /> Failed documents can be deleted and re-uploaded.
          </p>
        )}
      </div>

      {uploadOpen && (
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onUploaded={() => {
            queryClient.invalidateQueries({ queryKey: ['documents'] })
            setUploadOpen(false)
          }}
        />
      )}
    </div>
  )
}