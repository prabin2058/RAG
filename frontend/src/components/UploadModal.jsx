// Upload modal: drag-and-drop zone, file picker, progress + status polling.
import { useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { FileUp, Loader2, X } from 'lucide-react'
import { getDocumentStatus, uploadDocument } from '../api.js'

const MAX_SIZE_MB = 50

export default function UploadModal({ onClose, onUploaded }) {
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [statusText, setStatusText] = useState('')
  const fileInputRef = useRef(null)
  const queryClient = useQueryClient()

  const validate = (file) => {
    if (!file) return 'No file selected.'
    if (!file.name.toLowerCase().endsWith('.pdf')) return 'Only PDF files are allowed.'
    if (file.size > MAX_SIZE_MB * 1024 * 1024)
      return `File is too large (max ${MAX_SIZE_MB} MB).`
    return null
  }

  const pollStatus = async (docId) => {
    const interval = setInterval(async () => {
      try {
        const res = await getDocumentStatus(docId)
        if (res.status === 'ready') {
          clearInterval(interval)
          setStatusText('Done!')
          toast.success('Document processed and ready')
          await new Promise((r) => setTimeout(r, 400)) // let the user see the success state
          onUploaded()
          queryClient.invalidateQueries({ queryKey: ['documents'] })
        } else if (res.status === 'failed') {
          clearInterval(interval)
          toast.error(`Processing failed: ${res.error || 'unknown error'}`)
          setUploading(false)
          setStatusText('')
        } else {
          setStatusText('Extracting, chunking, and embedding…')
        }
      } catch (err) {
        clearInterval(interval)
        toast.error(err.message)
        setUploading(false)
        setStatusText('')
      }
    }, 2000)
  }

  const handleFile = useCallback(
    async (file) => {
      const error = validate(file)
      if (error) {
        toast.error(error)
        return
      }
      setUploading(true)
      setStatusText('Uploading…')
      try {
        const res = await uploadDocument(file)
        setStatusText('Queued — processing in the background…')
        pollStatus(res.doc_id)
      } catch (err) {
        toast.error(err.message)
        setUploading(false)
        setStatusText('')
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    if (!uploading && e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0])
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      <div className="relative w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Upload a PDF</h2>
          <button
            onClick={onClose}
            disabled={uploading}
            className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 disabled:opacity-40"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {!uploading ? (
          <>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
                dragOver ? 'border-indigo-500 bg-indigo-500/10' : 'border-zinc-700 hover:border-zinc-500'
              }`}
            >
              <FileUp size={32} className="text-zinc-400" />
              <p className="text-sm text-zinc-300">
                Drag &amp; drop a PDF here, or <span className="font-medium text-indigo-400">browse</span>
              </p>
              <p className="text-xs text-zinc-500">PDF only · up to {MAX_SIZE_MB} MB</p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
            />
          </>
        ) : (
          <div className="flex flex-col items-center gap-4 py-8">
            <Loader2 size={32} className="animate-spin text-indigo-400" />
            <p className="text-sm text-zinc-300">{statusText}</p>
            <p className="text-xs text-zinc-500">This can take a minute on CPU — embedding runs locally.</p>
          </div>
        )}
      </div>
    </div>
  )
}