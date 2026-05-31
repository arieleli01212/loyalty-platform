import React, { createContext, useContext, useState, useCallback } from 'react'
import { getAccessToken, clearTokens } from '../api/client'
import { login as apiLogin, register as apiRegister } from '../api/auth'

interface AuthContextValue {
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, businessName: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    return Boolean(getAccessToken())
  })

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password)
    setIsAuthenticated(true)
  }, [])

  const register = useCallback(
    async (email: string, password: string, businessName: string) => {
      await apiRegister(email, password, businessName)
      setIsAuthenticated(true)
    },
    [],
  )

  const logout = useCallback(() => {
    clearTokens()
    setIsAuthenticated(false)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
