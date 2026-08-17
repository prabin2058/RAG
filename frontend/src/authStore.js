// Zustand auth store: token + user session, persisted in localStorage.
// Exported as useAuthStore and used by AuthContext for React bindings.
import { create } from 'zustand'

const TOKEN_KEY = 'rag_token'
const USER_KEY = 'rag_user'

function loadStored() {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const user = JSON.parse(localStorage.getItem(USER_KEY) || 'null')
    return { token, user }
  } catch {
    return { token: null, user: null }
  }
}

const stored = loadStored()

export const useAuthStore = create((set) => ({
  token: stored.token,
  user: stored.user,
  // Set by RouterProvider's useNavigate once the app mounts (router context
  // isn't available inside the store).
  onUnauthorized: null,

  setSession: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    set({ token, user })
  },

  clearSession: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    set({ token: null, user: null })
  },

  handleUnauthorized: () => {
    const { token } = useAuthStore.getState()
    if (!token) return
    useAuthStore.getState().clearSession()
    useAuthStore.getState().onUnauthorized?.()
  },
}))