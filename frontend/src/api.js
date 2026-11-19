// Thin fetch wrapper around the FastAPI backend (v1 API).
// Injects the bearer token; on 401 the session is dropped and the user is
// redirected to /login (see AuthContext.handleUnauthorized).

import { useAuthStore } from './authStore.js'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function request(path, options = {}) {
  const token = useAuthStore.getState().token
  const headers = new Headers(options.headers || {})
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })

  if (res.status === 401 && !path.includes('/auth/login')) {
    useAuthStore.getState().handleUnauthorized()
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* keep default message */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export function uploadDocument(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request('/api/v1/upload', { method: 'POST', body: formData })
}

export function getDocumentStatus(docId) {
  return request(`/api/v1/documents/${docId}/status`)
}

export function listDocuments() {
  return request('/api/v1/documents')
}

export function deleteDocument(docId) {
  return request(`/api/v1/documents/${docId}`, { method: 'DELETE' })
}

export function sendQuery(docId, question, conversationId) {
  return request('/api/v1/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc_id: docId, question, conversation_id: conversationId || null }),
  })
}

export async function sendQueryStream(docId, question, conversationId, onToken, onDone, onError) {
  const token = useAuthStore.getState().token
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  try {
    const res = await fetch(`${BASE_URL}/api/v1/query/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ doc_id: docId, question, conversation_id: conversationId || null }),
    })

    if (!res.ok) {
      let detail = `Request failed (${res.status})`
      try {
        const body = await res.json()
        if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      } catch { /* keep default */ }
      throw new Error(detail)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // keep incomplete line in buffer
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const data = JSON.parse(line)
          if (data.error) {
            onError(new Error(data.error))
            return
          }
          if (data.done) {
            onDone(data)
            return
          }
          if (data.token) onToken(data.token)
        } catch { /* skip malformed lines */ }
      }
    }
    // Process any remaining buffer
    if (buffer.trim()) {
      try {
        const data = JSON.parse(buffer)
        if (data.error) onError(new Error(data.error))
        else onDone(data)
      } catch { /* ignore */ }
    }
  } catch (err) {
    onError(err)
  }
}

export function getConversationHistory(docId) {
  return request(`/api/v1/conversations/${docId}`)
}