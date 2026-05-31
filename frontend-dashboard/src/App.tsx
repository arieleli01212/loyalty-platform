import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { AuthGuard } from './components/AuthGuard'
import { Layout } from './components/Layout'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { BrandingPage } from './pages/BrandingPage'
import { ProgramsPage } from './pages/ProgramsPage'
import { CustomersPage } from './pages/CustomersPage'
import { EnrollmentQrPage } from './pages/EnrollmentQrPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <AuthGuard>
                <Layout />
              </AuthGuard>
            }
          >
            <Route path="/" element={<DashboardPage />} />
            <Route path="/branding" element={<BrandingPage />} />
            <Route path="/programs" element={<ProgramsPage />} />
            <Route path="/customers" element={<CustomersPage />} />
            <Route path="/qr" element={<EnrollmentQrPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
