'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import Link from 'next/link';

interface StockDetail {
  symbol: string;
  sector?: string;
  industry?: string;
  market_cap?: number;
  pe_ratio?: number;
  revenue_growth?: number;
  v2_score: number;
  quality_score: number;
  value_score: number;
  trajectory_score: number;
  current_price?: number;
  fifty_two_week_high?: number;
  fifty_two_week_low?: number;
}

function MetricCard({ label, value, unit = '', trend = null }: { label: string; value: any; unit?: string; trend?: 'up' | 'down' | null }) {
  return (
    <Card>
      <p className="text-slate-600 text-sm font-semibold uppercase tracking-wide">{label}</p>
      <div className="flex items-end gap-2 mt-2">
        <p className="text-2xl font-black text-slate-900">
          {typeof value === 'number' ? value.toLocaleString('en-US', { maximumFractionDigits: 2 }) : value}
        </p>
        <span className="text-slate-500 text-sm font-medium mb-1">{unit}</span>
      </div>
      {trend && (
        <p className={`text-sm font-semibold mt-2 ${trend === 'up' ? 'text-green-600' : 'text-red-600'}`}>
          {trend === 'up' ? '↑ Bullish' : '↓ Bearish'}
        </p>
      )}
    </Card>
  );
}

function ScoreGauge({ score, label }: { score: number; label: string }) {
  const percentage = score * 100;
  const getColor = (s: number) => {
    if (s >= 0.8) return 'from-green-400 to-green-500';
    if (s >= 0.6) return 'from-blue-400 to-blue-500';
    if (s >= 0.4) return 'from-yellow-400 to-yellow-500';
    return 'from-red-400 to-red-500';
  };

  const getGradient = getColor(score);
  const getLabel = (s: number) => {
    if (s >= 0.8) return 'Excellent';
    if (s >= 0.6) return 'Good';
    if (s >= 0.4) return 'Fair';
    return 'Poor';
  };

  return (
    <div className="text-center">
      <div className="mb-4">
        <div className="w-full h-3 bg-slate-200 rounded-full overflow-hidden">
          <div
            className={`h-full bg-gradient-to-r ${getGradient} transition-all duration-500`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
      <p className="text-sm font-semibold text-slate-600 uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-black text-slate-900 mt-1">{score.toFixed(3)}</p>
      <p className={`text-sm font-bold mt-2 ${getColor(score).includes('green') ? 'text-green-600' : getColor(score).includes('blue') ? 'text-blue-600' : getColor(score).includes('yellow') ? 'text-yellow-600' : 'text-red-600'}`}>
        {getLabel(score)}
      </p>
    </div>
  );
}

export default function StockDetailPage() {
  const params = useParams();
  const symbol = (params.symbol as string).toUpperCase();
  const [stock, setStock] = useState<StockDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStock = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getStockDetail(symbol);
        setStock(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch stock detail:', err);
        setError('Failed to load stock details');
        // Mock data for demonstration
        setStock({
          symbol,
          sector: 'Technology',
          industry: 'Consumer Electronics',
          market_cap: 2800000000000,
          pe_ratio: 32.5,
          revenue_growth: 0.042,
          v2_score: 0.825,
          quality_score: 0.91,
          value_score: 0.72,
          trajectory_score: 0.83,
          current_price: 189.50,
          fifty_two_week_high: 199.62,
          fifty_two_week_low: 164.08,
        });
      } finally {
        setLoading(false);
      }
    };

    fetchStock();
  }, [symbol]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
      </div>
    );
  }

  if (error || !stock) {
    return (
      <div className="space-y-6">
        <Link href="/">
          <Button variant="ghost" size="sm">
            ← Back
          </Button>
        </Link>
        <Card className="text-center py-12 border-2 border-red-200 bg-red-50">
          <p className="text-red-700 font-medium">{error || 'Stock not found'}</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <Link href="/">
          <Button variant="ghost" size="sm" className="mb-4">
            ← Back to Home
          </Button>
        </Link>
        <h1 className="text-5xl font-black text-slate-900">{stock.symbol}</h1>
        <p className="text-slate-600 mt-2">
          {stock.industry} • {stock.sector}
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-blue-50 border-2 border-blue-200 rounded-lg text-blue-700 text-sm font-medium">
          ℹ️ {error} — showing sample data for demonstration
        </div>
      )}

      {/* V2 Score Breakdown */}
      <Card className="border-2 border-blue-200 bg-gradient-to-br from-blue-50 to-white">
        <div className="mb-6">
          <h2 className="text-2xl font-black text-slate-900">V2 Mismatch Score Breakdown</h2>
          <p className="text-slate-600 mt-2">Our proprietary algorithm combining Quality, Value, and Trajectory</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Overall V2 Score */}
          <div>
            <ScoreGauge score={stock.v2_score} label="V2 Score" />
          </div>

          {/* Quality Score */}
          <div>
            <ScoreGauge score={stock.quality_score} label="Quality Score" />
            <p className="text-xs text-slate-600 text-center mt-3">
              Profitability, ROE, margins
            </p>
          </div>

          {/* Value Score */}
          <div>
            <ScoreGauge score={stock.value_score} label="Value Score" />
            <p className="text-xs text-slate-600 text-center mt-3">
              P/E, P/B, FCF multiples
            </p>
          </div>

          {/* Trajectory Score */}
          <div>
            <ScoreGauge score={stock.trajectory_score} label="Trajectory" />
            <p className="text-xs text-slate-600 text-center mt-3">
              Growth trends, momentum
            </p>
          </div>
        </div>

        <div className="mt-8 p-4 bg-white rounded-lg border border-slate-200">
          <p className="text-sm text-slate-700">
            <span className="font-bold">V2 Score Interpretation:</span> A geometric mean of Quality, Value, and Trajectory scores with sector-aware weighting. Scores above 0.75 indicate undervalued, high-quality opportunities with strong trajectory.
          </p>
        </div>
      </Card>

      {/* Key Metrics */}
      <div>
        <h2 className="text-2xl font-black text-slate-900 mb-6">Key Metrics</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <MetricCard label="Current Price" value={stock.current_price} unit="USD" />
          <MetricCard label="Market Cap" value={stock.market_cap ? (stock.market_cap / 1e9).toFixed(1) : 'N/A'} unit="B" />
          <MetricCard label="P/E Ratio" value={stock.pe_ratio?.toFixed(1) || 'N/A'} />
          <MetricCard label="Revenue Growth" value={stock.revenue_growth ? (stock.revenue_growth * 100).toFixed(1) : 'N/A'} unit="%" />
          <MetricCard label="52W High" value={stock.fifty_two_week_high?.toFixed(2) || 'N/A'} unit="USD" />
          <MetricCard label="52W Low" value={stock.fifty_two_week_low?.toFixed(2) || 'N/A'} unit="USD" />
        </div>
      </div>

      {/* Actions */}
      <Card className="border-2 border-slate-300 bg-gradient-to-r from-slate-50 to-white">
        <div className="flex flex-col md:flex-row gap-4">
          <Button variant="primary" size="lg" className="flex-1">
            + Add to Watchlist
          </Button>
          <Button variant="secondary" size="lg" className="flex-1">
            📊 Add to Portfolio
          </Button>
        </div>
      </Card>
    </div>
  );
}
