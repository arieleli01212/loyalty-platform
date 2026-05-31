import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, role } = useAuth()
  const { pathname } = useLocation()

  if (!isAuthenticated) return <Navigate to="/login" replace />

  // Staff can only access /scanner
  if (role === 'staff' && pathname !== '/scanner') {
    return <Navigate to="/scanner" replace />
  }

  return <>{children}</>
}
