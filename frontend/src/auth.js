// Auth API calls (unauthenticated — must NOT send the bearer token).
import { request } from './api.js'

export function registerUser(email, password) {
  return request('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
}

export function loginUser(email, password) {
  const body = new URLSearchParams({ username: email, password })
  return request('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
}

export function fetchMe() {
  return request('/api/v1/auth/me')
}