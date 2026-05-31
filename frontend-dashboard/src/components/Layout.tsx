import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/branding', label: 'Branding' },
  { to: '/programs', label: 'Programs' },
  { to: '/customers', label: 'Customers' },
  { to: '/qr', label: 'Enrollment QR' },
  { to: '/staff', label: 'Staff' },
  { to: '/scanner', label: 'Scanner' },
]

export function Layout() {
  const { logout } = useAuth()

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar */}
      <aside className="w-56 bg-indigo-800 text-white flex flex-col">
        <div className="px-6 py-5 font-bold text-lg border-b border-indigo-700">
          Loyalty Dashboard
        </div>
        <nav className="flex-1 py-4">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `block px-6 py-3 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-900 text-white'
                    : 'text-indigo-200 hover:bg-indigo-700 hover:text-white'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-6 py-4 border-t border-indigo-700">
          <button
            onClick={logout}
            className="text-indigo-300 hover:text-white text-sm transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
