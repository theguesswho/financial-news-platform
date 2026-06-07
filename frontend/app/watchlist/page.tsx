'use client';

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/lib/auth-store';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import Link from 'next/link';

interface WatchlistItem {
  symbol: string;
  v2_score: number;
  quality_score: number;
  value_score: number;
  trajectory_score: number;
  current_price?: number;
  sector?: string;
  industry?: string;
}

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full"
          style={{ width: `${score * 100}%` }}
        />
      </div>
      <span className="text-sm font-semibold text-slate-900">{score.toFixed(3)}</span>
    </div>
  );
}

export default function WatchlistPage() {
  const { user, isLoading } = useAuthStore();
  const router = useRouter();
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  useEffect(() => {
    const fetchWatchlist = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getWatchlist();
        setWatchlist(data || []);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch watchlist:', err);
        setError('Failed to load watchlist');
        // Mock data for demonstration
        setWatchlist([
          {
            symbol: 'AAPL',
            v2_score: 0.825,
            quality_score: 0.91,
            value_score: 0.72,
            trajectory_score: 0.83,
            current_price: 189.50,
            sector: 'Technology',
            industry: 'Consumer Electronics',
          },
          {
            symbol: 'MSFT',
            v2_score: 0.798,
            quality_score: 0.88,
            value_score: 0.75,
            trajectory_score: 0.80,
            current_price: 428.75,
            sector: 'Technology',
            industry: 'Software',
          },
        ]);
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchWatchlist();
    }
  }, [user]);

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
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-black text-slate-900">Your Watchlist</h1>
        <p className="text-slate-600 mt-2">Track stocks you're monitoring</p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-blue-50 border-2 border-blue-200 rounded-lg text-blue-700 text-sm font-medium">
          ℹ️ {error} — showing sample data for demonstration
        </div>
      )}

      {/* Watchlist Table */}
      {loading ? (
        <Card className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
          <p className="text-slate-600 mt-4">Loading your watchlist...</p>
        </Card>
      ) : watchlist.length === 0 ? (
        <Card className="text-center py-16">
          <div className="w-16 h-16 bg-gradient-to-br from-slate-100 to-slate-200 rounded-full mx-auto mb-4 flex items-center justify-center">
            <span className="text-3xl">👁️</span>
          </div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">No stocks yet</h3>
          <p className="text-slate-600 mb-6">Add stocks to your watchlist from the screener to track opportunities</p>
          <Link href="/screener">
            <Button variant="primary" size="md">
              Open Screener →
            </Button>
          </Link>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-200 bg-slate-50">
                <tr>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Symbol</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">V2 Score</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Quality</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Value</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Trajectory</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Sector</th>
                  <th className="text-center py-4 px-6 font-semibold text-slate-900">Action</th>
                </tr>
              </thead>
              <tbody>
                {watchlist.map((item, idx) => (
                  <tr key={item.symbol} className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${idx === watchlist.length - 1 ? 'border-b-0' : ''}`}>
                    <td className="py-4 px-6">
                      <Link href={`/stocks/${item.symbol}`} className="font-black text-blue-600 hover:text-blue-700 transition-colors text-lg">
                        {item.symbol}
                      </Link>
                    </td>
                    <td className="py-4 px-6">
                      <ScoreBar score={item.v2_score} />
                    </td>
                    <td className="py-4 px-6">
                      <ScoreBar score={item.quality_score} />
                    </td>
                    <td className="py-4 px-6">
                      <ScoreBar score={item.value_score} />
                    </td>
                    <td className="py-4 px-6">
                      <ScoreBar score={item.trajectory_score} />
                    </td>
                    <td className="py-4 px-6">
                      <span className="text-sm font-medium text-slate-600">{item.sector || 'N/A'}</span>
                    </td>
                    <td className="py-4 px-6 text-center">
                      <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700">
                        Remove
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
