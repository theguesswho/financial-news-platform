'use client';

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/lib/auth-store';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import Link from 'next/link';

interface Holding {
  symbol: string;
  shares: number;
  entry_price: number;
  current_price: number;
  v2_score: number;
  sector?: string;
}

interface PortfolioSummary {
  total_value: number;
  total_cost: number;
  unrealized_gain: number;
  unrealized_gain_pct: number;
  holdings_count: number;
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

export default function PortfolioPage() {
  const { user, isLoading } = useAuthStore();
  const router = useRouter();
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  useEffect(() => {
    const fetchPortfolio = async () => {
      try {
        setLoading(true);
        const [portfolioData, summaryData] = await Promise.all([
          apiClient.getPortfolio(),
          apiClient.getPortfolioSummary(),
        ]);
        setHoldings(portfolioData || []);
        setSummary(summaryData || null);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch portfolio:', err);
        setError('Failed to load portfolio');
        // Mock data for demonstration
        setSummary({
          total_value: 125000,
          total_cost: 100000,
          unrealized_gain: 25000,
          unrealized_gain_pct: 25,
          holdings_count: 3,
        });
        setHoldings([
          {
            symbol: 'AAPL',
            shares: 50,
            entry_price: 150,
            current_price: 189.50,
            v2_score: 0.825,
            sector: 'Technology',
          },
          {
            symbol: 'MSFT',
            shares: 30,
            entry_price: 350,
            current_price: 428.75,
            v2_score: 0.798,
            sector: 'Technology',
          },
          {
            symbol: 'TSLA',
            shares: 20,
            entry_price: 200,
            current_price: 242.50,
            v2_score: 0.712,
            sector: 'Automotive',
          },
        ]);
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchPortfolio();
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
        <h1 className="text-4xl font-black text-slate-900">Your Portfolio</h1>
        <p className="text-slate-600 mt-2">Track your stock holdings and performance</p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-blue-50 border-2 border-blue-200 rounded-lg text-blue-700 text-sm font-medium">
          ℹ️ {error} — showing sample data for demonstration
        </div>
      )}

      {/* Portfolio Summary */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card>
            <p className="text-slate-600 text-sm font-semibold uppercase tracking-wide">Total Value</p>
            <p className="text-3xl font-black text-slate-900 mt-2">${summary.total_value.toLocaleString()}</p>
            <p className="text-slate-500 text-sm mt-1">Current portfolio value</p>
          </Card>

          <Card>
            <p className="text-slate-600 text-sm font-semibold uppercase tracking-wide">Total Cost</p>
            <p className="text-3xl font-black text-slate-900 mt-2">${summary.total_cost.toLocaleString()}</p>
            <p className="text-slate-500 text-sm mt-1">Amount invested</p>
          </Card>

          <Card className={summary.unrealized_gain >= 0 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}>
            <p className={`text-sm font-semibold uppercase tracking-wide ${summary.unrealized_gain >= 0 ? 'text-green-700' : 'text-red-700'}`}>
              Unrealized Gain
            </p>
            <p className={`text-3xl font-black mt-2 ${summary.unrealized_gain >= 0 ? 'text-green-900' : 'text-red-900'}`}>
              ${Math.abs(summary.unrealized_gain).toLocaleString()}
            </p>
            <p className={`text-sm mt-1 ${summary.unrealized_gain >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {summary.unrealized_gain >= 0 ? '+' : '-'}{summary.unrealized_gain_pct.toFixed(1)}%
            </p>
          </Card>

          <Card>
            <p className="text-slate-600 text-sm font-semibold uppercase tracking-wide">Holdings</p>
            <p className="text-3xl font-black text-slate-900 mt-2">{summary.holdings_count}</p>
            <p className="text-slate-500 text-sm mt-1">Active positions</p>
          </Card>
        </div>
      )}

      {/* Holdings Table */}
      {loading ? (
        <Card className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
          <p className="text-slate-600 mt-4">Loading your portfolio...</p>
        </Card>
      ) : holdings.length === 0 ? (
        <Card className="text-center py-16">
          <div className="w-16 h-16 bg-gradient-to-br from-slate-100 to-slate-200 rounded-full mx-auto mb-4 flex items-center justify-center">
            <span className="text-3xl">📊</span>
          </div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">No holdings yet</h3>
          <p className="text-slate-600 mb-6">Add stocks to your portfolio to start tracking your investments</p>
          <Link href="/screener">
            <Button variant="primary" size="md">
              Find Stocks →
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
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Shares</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Entry Price</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Current Price</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">Gain/Loss</th>
                  <th className="text-left py-4 px-6 font-semibold text-slate-900">V2 Score</th>
                  <th className="text-center py-4 px-6 font-semibold text-slate-900">Action</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((holding, idx) => {
                  const gain = (holding.current_price - holding.entry_price) * holding.shares;
                  const gainPct = ((holding.current_price - holding.entry_price) / holding.entry_price) * 100;
                  const isPositive = gain >= 0;

                  return (
                    <tr key={holding.symbol} className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${idx === holdings.length - 1 ? 'border-b-0' : ''}`}>
                      <td className="py-4 px-6">
                        <Link href={`/stocks/${holding.symbol}`} className="font-black text-blue-600 hover:text-blue-700 transition-colors text-lg">
                          {holding.symbol}
                        </Link>
                      </td>
                      <td className="py-4 px-6">
                        <span className="text-sm font-medium text-slate-900">{holding.shares}</span>
                      </td>
                      <td className="py-4 px-6">
                        <span className="text-sm font-medium text-slate-600">${holding.entry_price.toFixed(2)}</span>
                      </td>
                      <td className="py-4 px-6">
                        <span className="text-sm font-bold text-slate-900">${holding.current_price.toFixed(2)}</span>
                      </td>
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-2">
                          <span className={`text-sm font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                            {isPositive ? '+' : '-'}${Math.abs(gain).toFixed(0)}
                          </span>
                          <span className={`text-xs font-semibold px-2 py-1 rounded ${isPositive ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                            {isPositive ? '+' : '-'}{Math.abs(gainPct).toFixed(1)}%
                          </span>
                        </div>
                      </td>
                      <td className="py-4 px-6">
                        <ScoreBar score={holding.v2_score} />
                      </td>
                      <td className="py-4 px-6 text-center">
                        <Button variant="ghost" size="sm" className="text-red-600 hover:text-red-700">
                          Remove
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
