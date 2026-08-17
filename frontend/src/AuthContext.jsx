// AuthContext: React bindings around useAuthStore — session restore,
// login/register/logout actions, and cross-component access to the user.
import { createContext, useCallback, useContext, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAuthStore } from './authStore.js'
import { fetchMe, loginUser, registerUser } from './auth.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const navigate = useNavigate()
  const { token, user, setSession, clearSession, onUnauthorized } = useAuthStore()

  // Wire the router into the store so api.js 401s can redirect.
  useEffect(() => {
    useAuthStore.setState({ onUnauthorized: () => navigate('/login') })
  }, [navigate])

  // On mount: validate the stored token against /auth/me.
  useEffect(() => {
    if (!token) return
    let cancelled = false
    fetchMe()
      .then((me) => {
        if (!cancelled) setSession(token, me)
      })
      .catch(() => {
        if (!cancelled) clearSession()
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = useCallback(
    async (email, password) => {
      const res = await loginUser(email, password)
      setSession(res.access_token, res.user)
      navigate('/')
    },
    [navigate, setSession],
  )

  const register = useCallback(
    async (email, password) => {
      const res = await registerUser(email, password)
      setSession(res.access_token, res.user)
      navigate('/')
    },
    [navigate, setSession],
  )

  const logout = useCallback(() => {
    clearSession()
    toast.success('Logged out')
    navigate('/login')
  }, [clearSession, navigate])

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}