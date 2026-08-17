// Thin fetch wrapper around the FastAPI backend.

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, options)
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep default message */
    }
    throw new Error(detail)
  }
  return res.json()
}

export function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/upload', { method: 'POST', body: formData })
}

export function getDocumentStatus(docId) {
  return request(`/documents/${docId}/status`)
}

export function listDocuments() {
  return request('/documents')
}

export function deleteDocument(docId) {
  return request(`/documents/${docId}`, { method: 'DELETE' })
}

export function sendQuery(docId, question, conversationId) {
  return request('/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_id: docId, question, conversation_id: conversationId || null }),
  })
}

export function getConversationHistory(docId) {
  return request(`/conversations/${docId}`)
}