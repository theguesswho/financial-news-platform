'use client';

import { useAuthStore } from '@/lib/auth-store';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/common/Button';
import { useEffect } from 'react';

interface MainLayoutProps {
  children: React.ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const { user, logout, checkAuth } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      <nav className="bg-white shadow-md border-b border-slate-200 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <Link href="/" className="text-2xl font-black bg-gradient-to-r from-blue-600 to-blue-700 bg-clip-text text-transparent hover:opacity-80 transition-opacity">
            FinanceIQ
          </Link>

          <div className="flex items-center gap-3">
            {user ? (
              <>
                <Link href="/dashboard" className="text-slate-700 font-medium hover:text-blue-600 transition-colors px-3 py-1.5">
                  Dashboard
                </Link>
                <Link href="/screener" className="text-slate-700 font-medium hover:text-blue-600 transition-colors px-3 py-1.5">
                  Screener
                </Link>
                <Link href="/watchlist" className="text-slate-700 font-medium hover:text-blue-600 transition-colors px-3 py-1.5">
                  Watchlist
                </Link>
                <Link href="/portfolio" className="text-slate-700 font-medium hover:text-blue-600 transition-colors px-3 py-1.5">
                  Portfolio
                </Link>
                <div className="w-px h-6 bg-slate-200 mx-2"></div>
                <span className="text-slate-600 text-sm font-medium">{user.name}</span>
                <Button onClick={handleLogout} variant="ghost" size="sm">
                  Logout
                </Button>
              </>
            ) : (
              <>
                <Link href="/login">
                  <Button variant="ghost" size="sm">
                    Login
                  </Button>
                </Link>
                <Link href="/register">
                  <Button variant="primary" size="sm">
                    Get Started
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {children}
      </main>
    </div>
  );
}
