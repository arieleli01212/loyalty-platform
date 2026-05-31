import React, { createContext, useContext, useState, useCallback } from 'react'
import { getAccessToken, clearTokens, apiFetch } from '../api/client'
import { login as apiLogin, register as apiRegister } from '../api/auth'

export type UserRole = 'owner' | 'staff'

interface AuthContextValue {
  isAuthenticated: boolean
  role: UserRole | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, businessName: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

async function fetchRole(): Promise<UserRole | null> {
  try {
    const data = await apiFetch<{ role: string }>('/api/v1/auth/me')
    return data.role as UserRole
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => Boolean(getAccessToken()))
  const [role, setRole] = useState<UserRole | null>(() => {
    return (localStorage.getItem('user_role') as UserRole | null)
  })

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password)
    const r = await fetchRole()
    setRole(r)
    if (r) localStorage.setItem('user_role', r)
    setIsAuthenticated(true)
  }, [])

  const register = useCallback(async (email: string, password: string, businessName: string) => {
    await apiRegister(email, password, businessName)
    setRole('owner')
    localStorage.setItem('user_role', 'owner')
    setIsAuthenticated(true)
  }, [])

  const logout = useCallback(() => {
    clearTokens()
    localStorage.removeItem('user_role')
    setRole(null)
    setIsAuthenticated(false)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, role, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
