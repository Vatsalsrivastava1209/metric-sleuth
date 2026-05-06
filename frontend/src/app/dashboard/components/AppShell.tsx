'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Activity, Bell, CreditCard, Database,
  FileText, History, Menu, Settings, X,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const primaryNav = [
  { href: '/dashboard',          label: 'Inbox',    icon: Bell },
  { href: '/dashboard/datasets', label: 'Clients',  icon: Database },
  { href: '/dashboard/reports',  label: 'Reports',  icon: FileText },
  { href: '/dashboard/ops',      label: 'Health',   icon: Activity },
  { href: '/dashboard/memory',   label: 'History',  icon: History },
]

const secondaryNav = [
  { href: '/dashboard/billing',  label: 'Billing',  icon: CreditCard },
  { href: '/dashboard/settings', label: 'Settings', icon: Settings },
]

function NavItem({
  href, label, icon: Icon, active, onClick,
}: {
  href: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  active: boolean
  onClick?: () => void
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        'group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
        active ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
      )}
    >
      <Icon className={cn(
        'h-4 w-4 shrink-0 transition-colors',
        active ? 'text-amber-400' : 'text-slate-500 group-hover:text-amber-400'
      )} />
      {label}
      {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-amber-400" />}
    </Link>
  )
}

function SignOutButton({ action }: { action: () => Promise<void> }) {
  return (
    <form action={action}>
      <button
        type="submit"
        className="p-1.5 rounded-md hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-colors shrink-0"
        title="Sign out"
      >
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h6a2 2 0 012 2v1" />
        </svg>
      </button>
    </form>
  )
}

export function AppShell({
  userEmail,
  signoutAction,
  children,
}: {
  userEmail: string
  signoutAction: () => Promise<void>
  children: React.ReactNode
}) {
  const [openPath, setOpenPath] = useState<string | null>(null)
  const pathname = usePathname()
  const open = openPath === pathname

  // Lock body scroll when drawer is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [open])

  const isActive = (href: string) =>
    href === '/dashboard' ? pathname === '/dashboard' : pathname.startsWith(href)

  const navLinks = (onNav?: () => void) => (
    <>
      <nav className="flex-1 px-3 pt-4 pb-2 space-y-0.5 overflow-y-auto">
        {primaryNav.map((item) => (
          <NavItem key={item.href} {...item} active={isActive(item.href)} onClick={onNav} />
        ))}
      </nav>
      <div className="px-3 pb-3 pt-3 space-y-0.5 border-t border-slate-800/70">
        {secondaryNav.map((item) => (
          <NavItem key={item.href} {...item} active={isActive(item.href)} onClick={onNav} />
        ))}
      </div>
    </>
  )

  const userFooter = (
    <div className="px-4 py-3 border-t border-slate-800/70">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[11px] text-slate-500">{userEmail}</div>
        </div>
        <SignOutButton action={signoutAction} />
      </div>
    </div>
  )

  const logo = (
    <div className="flex items-center">
      <Activity className="h-4 w-4 text-amber-400 mr-2.5 shrink-0" />
      <span className="font-semibold text-[15px] tracking-tight text-white">Metric Sleuth</span>
    </div>
  )

  return (
    <div className="flex h-dvh overflow-hidden bg-slate-950 text-slate-100">

      {/* ── Desktop sidebar (md+) ────────────────────────────────────────── */}
      <aside className="hidden md:flex w-56 border-r border-slate-800/70 bg-slate-950 flex-col shrink-0">
        <div className="h-14 flex items-center px-5 border-b border-slate-800/70">
          {logo}
        </div>
        {navLinks()}
        {userFooter}
      </aside>

      {/* ── Mobile overlay ───────────────────────────────────────────────── */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-slate-950/80 backdrop-blur-sm md:hidden"
          onClick={() => setOpenPath(null)}
          aria-hidden="true"
        />
      )}

      {/* ── Mobile drawer ────────────────────────────────────────────────── */}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-64 bg-slate-950 border-r border-slate-800/70 flex flex-col',
          'transition-transform duration-200 ease-in-out md:hidden',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
        aria-modal="true"
        role="dialog"
      >
        <div className="h-14 flex items-center justify-between px-5 border-b border-slate-800/70">
          {logo}
          <button
            onClick={() => setOpenPath(null)}
            className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-white transition-colors -mr-1"
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {navLinks(() => setOpenPath(null))}
        {userFooter}
      </aside>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Mobile top bar */}
        <header className="md:hidden h-14 flex items-center justify-between px-4 border-b border-slate-800/70 bg-slate-950 shrink-0">
          <button
            onClick={() => setOpenPath(pathname)}
            className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          {logo}
          <div className="w-8" aria-hidden="true" />
        </header>

        <main className="flex-1 overflow-y-auto focus:outline-none">
          <div className="py-6 md:py-8">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-8">
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
