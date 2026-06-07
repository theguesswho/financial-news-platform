'use client';

import { useEffect, useState } from 'react';
import { useAuthStore } from '@/lib/auth-store';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import Link from 'next/link';

interface Stock {
  symbol: string;
  v2_score: number;
  quality_score: number;
  value_score: number;
  trajectory_score: number;
  current_price?: number;
  sector?: string;
  pe_ratio?: number;
  revenue_growth?: number;
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

export default function ScreenerPage() {
  const { user } = useAuthStore();
  const router = useRouter();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [minScore, setMinScore] = useState('0.70');
  const [sector, setSector] = useState('');
  const [maxPe, setMaxPe] = useState('');
  const [limit, setLimit] = useState('50');

  useEffect(() => {
    fetchStocks();
  }, []);

  const fetchStocks = async () => {
    try {
      setLoading(true);
      const filters: any = {
        limit: parseInt(limit),
      };
      if (minScore) filters.min_score = parseFloat(minScore);
      if (sector) filters.sector = sector;
      if (maxPe) filters.max_pe = parseFloat(maxPe);

      const data = await apiClient.getStocks(filters);
      setStocks(data || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch stocks:', err);
      setError('Failed to load screener results');
      // Mock data for demonstration
      setStocks([
        {
          symbol: 'AAPL',
          v2_score: 0.825,
          quality_score: 0.91,
          value_score: 0.72,
          trajectory_score: 0.83,
          current_price: 189.50,
          sector: 'Technology',
          pe_ratio: 32.5,
          revenue_growth: 0.042,
        },
        {
          symbol: 'MSFT',
          v2_score: 0.798,
          quality_score: 0.88,
          value_score: 0.75,
          trajectory_score: 0.80,
          current_price: 428.75,
          sector: 'Technology',
          pe_ratio: 35.2,
          revenue_growth: 0.078,
        },
        {
          symbol: 'NVDA',
          v2_score: 0.812,
          quality_score: 0.92,
          value_score: 0.68,
          trajectory_score: 0.85,
          current_price: 875.40,
          sector: 'Technology',
          pe_ratio: 78.3,
          revenue_growth: 0.201,
        },
        {
          symbol: 'JPM',
          v2_score: 0.754,
          quality_score: 0.82,
          value_score: 0.78,
          trajectory_score: 0.71,
          current_price: 198.65,
          sector: 'Financials',
          pe_ratio: 12.4,
          revenue_growth: 0.031,
        },
        {
          symbol: 'JNJ',
          v2_score: 0.768,
          quality_score: 0.85,
          value_score: 0.81,
          trajectory_score: 0.68,
          current_price: 159.20,
          sector: 'Healthcare',
          pe_ratio: 25.6,
          revenue_growth: 0.022,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleFilter = () => {
    fetchStocks();
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-4xl font-black text-slate-900">Stock Screener</h1>
        <p className="text-slate-600 mt-2">Find undervalued opportunities using V2 mismatch scores</p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-blue-50 border-2 border-blue-200 rounded-lg text-blue-700 text-sm font-medium">
          ℹ️ {error} — showing sample data for demonstration
        </div>
      )}

      {/* Filters */}
      <Card className="border-2 border-blue-200 bg-gradient-to-br from-blue-50 to-white">
        <div className="mb-6">
          <h2 className="text-lg font-bold text-slate-900">Filters</h2>
          <p className="text-slate-600 text-sm mt-1">Refine your search for investment opportunities</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Input
            label="Min V2 Score"
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            placeholder="0.70"
          />

          <Input
            label="Sector"
            type="text"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            placeholder="e.g., Technology"
          />

          <Input
            label="Max P/E Ratio"
            type="number"
            min="0"
            step="5"
            value={maxPe}
            onChange={(e) => setMaxPe(e.target.value)}
            placeholder="50"
          />

          <Input
            label="Limit Results"
            type="number"
            min="10"
            max="500"
            step="10"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            placeholder="50"
          />
        </div>

        <Button variant="primary" onClick={handleFilter} className="mt-6 w-full">
          Apply Filters
        </Button>
      </Card>

      {/* Results */}
      {loading ? (
        <Card className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
          <p className="text-slate-600 mt-4">Running screener...</p>
        </Card>
      ) : stocks.length === 0 ? (
        <Card className="text-center py-16">
          <div className="w-16 h-16 bg-gradient-to-br from-slate-100 to-slate-200 rounded-full mx-auto mb-4 flex items-center justify-center">
            <span className="text-3xl">🔍</span>
          </div>
          <h3 className="text-lg font-bold text-slate-900 mb-2">No results found</h3>
          <p className="text-slate-600 mb-6">Try adjusting your filters to find more opportunities</p>
          <Button variant="secondary" onClick={() => {
            setMinScore('0.70');
            setSector('');
            setMaxPe('');
            setLimit('50');
            fetchStocks();
          }}>
            Reset Filters
          </Button>
        </Card>
      ) : (
        <>
          <div className="flex justify-between items-center">
            <p className="text-slate-600 font-medium">{stocks.length} opportunities found</p>
          </div>

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
                    <th className="text-left py-4 px-6 font-semibold text-slate-900">P/E</th>
                    <th className="text-center py-4 px-6 font-semibold text-slate-900">Action</th>
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
                      <td className="py-4 px-6">
                        <span className="text-sm font-medium text-slate-600">{stock.sector || 'N/A'}</span>
                      </td>
                      <td className="py-4 px-6">
                        <span className="text-sm font-medium text-slate-900">{stock.pe_ratio?.toFixed(1) || 'N/A'}</span>
                      </td>
                      <td className="py-4 px-6 text-center">
                        <Button variant="secondary" size="sm">
                          View →
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
