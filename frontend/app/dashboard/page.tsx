'use client';

import { useAuthStore } from '@/lib/auth-store';
import { useRouter } from 'next/navigation';
import { Card } from '@/components/common/Card';
import { useEffect } from 'react';
import Link from 'next/link';
import { Button } from '@/components/common/Button';

export default function DashboardPage() {
  const { user, isLoading } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="space-y-12">
      {/* Welcome Section */}
      <div className="bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-xl p-8 md:p-10">
        <h1 className="text-4xl md:text-5xl font-black mb-2">Welcome, {user.name}! 👋</h1>
        <p className="text-blue-100 text-lg">Manage your watchlist, portfolio, and discover new investment opportunities.</p>
      </div>

      {/* Quick Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="group">
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="text-slate-600 text-sm font-semibold uppercase tracking-wide">Watchlist</p>
              <p className="text-4xl font-black text-slate-900 mt-2">0</p>
              <p className="text-slate-500 text-sm mt-1">stocks tracked</p>
            </div>
            <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-200 rounded-lg group-hover:shadow-lg transition-shadow"></div>
          </div>
          <Link href="/watchlist">
            <Button variant="secondary" size="sm" className="w-full mt-4">
              View Watchlist →
            </Button>
          </Link>
        </Card>

        <Card className="group">
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="text-slate-600 text-sm font-semibold uppercase tracking-wide">Portfolio</p>
              <p className="text-4xl font-black text-slate-900 mt-2">0</p>
              <p className="text-slate-500 text-sm mt-1">holdings</p>
            </div>
            <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-200 rounded-lg group-hover:shadow-lg transition-shadow"></div>
          </div>
          <Link href="/portfolio">
            <Button variant="secondary" size="sm" className="w-full mt-4">
              View Portfolio →
            </Button>
          </Link>
        </Card>

        <Card className="group">
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="text-slate-600 text-sm font-semibold uppercase tracking-wide">Screener</p>
              <p className="text-4xl font-black text-slate-900 mt-2">∞</p>
              <p className="text-slate-500 text-sm mt-1">opportunities</p>
            </div>
            <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-200 rounded-lg group-hover:shadow-lg transition-shadow"></div>
          </div>
          <Link href="/screener">
            <Button variant="secondary" size="sm" className="w-full mt-4">
              Open Screener →
            </Button>
          </Link>
        </Card>
      </div>

      {/* Action Section */}
      <Card className="border-2 border-blue-200 bg-gradient-to-br from-blue-50 to-white">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between">
          <div>
            <h3 className="text-2xl font-black text-slate-900 mb-2">Ready to find hidden gems?</h3>
            <p className="text-slate-600">Explore our stock screener to discover high-quality, undervalued opportunities.</p>
          </div>
          <Link href="/screener" className="mt-4 md:mt-0 md:ml-6">
            <Button variant="primary" size="lg">
              Launch Screener →
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  );
}
