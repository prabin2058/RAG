// Route guards: require an authenticated session, or require a guest
// (already-logged-in users are bounced away from /login and /register).
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../authStore.js'

export function RequireAuth({ children }) {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  return children
}

export function RequireGuest({ children }) {
  const token = useAuthStore((s) => s.token)
  if (token) return <Navigate to="/" replace />
  return children
}