'use client';

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/lib/auth-store';
import { apiClient } from '@/lib/api-client';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import Link from 'next/link';

interface Stock {
  symbol: string;
  v2_score: number;
  quality_score: number;
  value_score: number;
  trajectory_score: number;
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

export default function HomePage() {
  const { user } = useAuthStore();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStocks = async () => {
      try {
        const data = await apiClient.getStocks({ min_score: 0.70, limit: 10 });
        setStocks(data);
      } catch (error) {
        console.error('Failed to fetch stocks:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStocks();
  }, []);

  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900 text-white p-12 md:p-16">
        <div className="relative z-10">
          <div className="inline-block mb-4 px-4 py-1.5 bg-blue-500/30 rounded-full border border-blue-400/50">
            <span className="text-sm font-semibold text-blue-100">AI-Powered Stock Analysis</span>
          </div>
          <h1 className="text-5xl md:text-6xl font-black mb-6 leading-tight">
            Find Hidden<br />
            <span className="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
              Investment Gems
            </span>
          </h1>
          <p className="text-xl text-slate-200 mb-8 max-w-2xl">
            Discover undervalued companies using advanced V2 mismatch scoring. Quality, Value, Trajectory — all in one intelligent metric.
          </p>
          {!user && (
            <div className="flex flex-col sm:flex-row gap-4">
              <Link href="/register">
                <Button variant="primary" size="lg" className="min-w-[180px]">
                  Get Started Free
                </Button>
              </Link>
              <Link href="/login">
                <Button variant="outline" size="lg" className="min-w-[180px] border-white/30 text-white hover:bg-white/10">
                  Sign In
                </Button>
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* Top Stocks Section */}
      <div>
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-3xl font-black text-slate-900">Top Opportunities</h2>
            <p className="text-slate-600 mt-1">Highest-scoring stocks this week</p>
          </div>
          {user && (
            <Link href="/screener">
              <Button variant="secondary" size="md">
                View Screener →
              </Button>
            </Link>
          )}
        </div>

        {loading ? (
          <Card className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
            <p className="text-slate-600 mt-4">Loading opportunities...</p>
          </Card>
        ) : stocks.length === 0 ? (
          <Card className="text-center py-12">
            <p className="text-slate-600 text-lg">No opportunities found. Try adjusting filters.</p>
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
                    {user && <th className="text-center py-4 px-6 font-semibold text-slate-900">Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((stock, idx) => (
                    <tr key={stock.symbol} className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${idx === stocks.length - 1 ? 'border-b-0' : ''}`}>
                      <td className="py-4 px-6">
                        <Link href={`/stocks/${stock.symbol}`} className="font-black text-blue-600 hover:text-blue-700 transition-colors text-lg">
                          {stock.symbol}
                        </Link>
                      </td>
                      <td className="py-4 px-6">
                        <ScoreBar score={stock.v2_score} />
                      </td>
                      <td className="py-4 px-6">
                        <ScoreBar score={stock.quality_score} />
                      </td>
                      <td className="py-4 px-6">
                        <ScoreBar score={stock.value_score} />
                      </td>
                      <td className="py-4 px-6">
                        <ScoreBar score={stock.trajectory_score} />
                      </td>
                      {user && (
                        <td className="py-4 px-6 text-center">
                          <Button variant="secondary" size="sm">
                            + Add
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>

      {/* Features Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <Card className="group">
          <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-200 rounded-lg mb-4 group-hover:shadow-lg transition-shadow"></div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">Intelligent Scoring</h3>
          <p className="text-slate-600 leading-relaxed">
            Our proprietary V2 algorithm combines Quality, Value, and Trajectory with sector-aware weighting to identify truly undervalued opportunities.
          </p>
        </Card>
        <Card className="group">
          <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-200 rounded-lg mb-4 group-hover:shadow-lg transition-shadow"></div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">Smart Watchlist</h3>
          <p className="text-slate-600 leading-relaxed">
            Track stocks with custom alerts. Monitor entry prices, V2 score changes, and get notified when opportunities meet your criteria.
          </p>
        </Card>
        <Card className="group">
          <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-200 rounded-lg mb-4 group-hover:shadow-lg transition-shadow"></div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">Portfolio Analytics</h3>
          <p className="text-slate-600 leading-relaxed">
            Manage your holdings, track P&L, and analyze portfolio performance with real-time V2 score updates for each position.
          </p>
        </Card>
      </div>
    </div>
  );
}
