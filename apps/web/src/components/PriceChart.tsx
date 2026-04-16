import { Card } from './ui/card';
import { Tabs, TabsList, TabsTrigger } from './ui/tabs';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useState, useEffect, useMemo } from 'react';
import { MarketApi } from '../lib/api';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Checkbox } from './ui/checkbox';
import { Label } from './ui/label';

interface PriceChartProps {
  selectedGPU: string;
}

type PricePoint = { time: string; price: number; volume: number };

export function PriceChart({ selectedGPU }: PriceChartProps) {
  const [data, setData] = useState<PricePoint[]>([]);
  const [timeframe, setTimeframe] = useState('24H');
  const [comparisonGPU, setComparisonGPU] = useState('A100');
  const [comparisonData, setComparisonData] = useState<PricePoint[]>([]);
  const [showComparison, setShowComparison] = useState(true);
  const [showVolume, setShowVolume] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      const [tape, book] = await Promise.all([
        MarketApi.getLiveTape({ gpu_model: selectedGPU, limit: 120 }),
        MarketApi.getLiveOrderBook({ gpu_model: selectedGPU }),
      ]);
      if (cancelled) return;
      const rows = [...tape].reverse().map((trade) => ({
        time: new Date(trade.created_at).toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }),
        price: trade.price_per_ngh,
        volume: trade.quantity_ngh,
      }));
      if (rows.length === 0) {
        const fallback =
          book.best_bid != null && book.best_ask != null
            ? (book.best_bid + book.best_ask) / 2
            : (book.best_bid ?? book.best_ask ?? 0);
        if (fallback > 0) {
          rows.push({
            time: new Date().toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            }),
            price: Number(fallback.toFixed(2)),
            volume: 0,
          });
        }
      }
      setData(rows.slice(-80));
    }

    void refresh().catch(() => undefined);
    const interval = setInterval(() => {
      void refresh().catch(() => undefined);
    }, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [selectedGPU]);

  useEffect(() => {
    if (!showComparison || comparisonGPU === selectedGPU) return;
    let cancelled = false;
    async function refreshComparison() {
      const [tape, book] = await Promise.all([
        MarketApi.getLiveTape({ gpu_model: comparisonGPU, limit: 120 }),
        MarketApi.getLiveOrderBook({ gpu_model: comparisonGPU }),
      ]);
      if (cancelled) return;
      const rows = [...tape].reverse().map((trade) => ({
        time: new Date(trade.created_at).toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }),
        price: trade.price_per_ngh,
        volume: trade.quantity_ngh,
      }));
      if (rows.length === 0) {
        const fallback =
          book.best_bid != null && book.best_ask != null
            ? (book.best_bid + book.best_ask) / 2
            : (book.best_bid ?? book.best_ask ?? 0);
        if (fallback > 0) {
          rows.push({
            time: new Date().toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            }),
            price: Number(fallback.toFixed(2)),
            volume: 0,
          });
        }
      }
      setComparisonData(rows.slice(-80));
    }
    void refreshComparison().catch(() => undefined);
    const interval = setInterval(() => {
      void refreshComparison().catch(() => undefined);
    }, 4500);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [comparisonGPU, selectedGPU, showComparison]);

  const currentPrice = data[data.length - 1]?.price || 0;
  const previousPrice = data[0]?.price || 0;
  const priceChange = currentPrice - previousPrice;
  const percentChange =
    previousPrice > 0 ? ((priceChange / previousPrice) * 100).toFixed(2) : '0.00';
  const comparisonCurrentPrice = comparisonData[comparisonData.length - 1]?.price || 0;
  const alignedData = useMemo(() => {
    const base = data.map((point) => ({
      ...point,
      referencePrice: undefined as number | undefined,
      normalizedPrice: currentPrice > 0 ? (point.price / currentPrice) * 100 : 0,
    }));
    if (!showComparison || comparisonGPU === selectedGPU || comparisonData.length === 0) {
      return base;
    }
    const step = Math.max(1, Math.floor(comparisonData.length / Math.max(base.length, 1)));
    return base.map((point, index) => {
      const ref = comparisonData[Math.min(comparisonData.length - 1, index * step)];
      return {
        ...point,
        referencePrice: ref?.price,
      };
    });
  }, [comparisonData, comparisonGPU, currentPrice, data, selectedGPU, showComparison]);
  const chartData = useMemo(() => {
    if (!showVolume) return alignedData;
    return alignedData.map((point) => ({ ...point, volumeScale: point.volume }));
  }, [alignedData, showVolume]);

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2>{selectedGPU}</h2>
          <div className="flex items-baseline gap-3 mt-2">
            <span className="text-3xl text-slate-100">${currentPrice.toFixed(2)}</span>
            <span className="text-sm text-slate-400">/NGH</span>
            <span className={`text-sm ${parseFloat(percentChange) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {parseFloat(percentChange) >= 0 ? '+' : ''}{percentChange}%
            </span>
          </div>
          {showComparison && comparisonGPU !== selectedGPU && comparisonCurrentPrice > 0 ? (
            <div className="mt-1 text-xs text-slate-400">
              Comparison: {comparisonGPU} ${comparisonCurrentPrice.toFixed(2)} /NGH
            </div>
          ) : null}
        </div>
        <div className="space-y-3">
          <Tabs value={timeframe} onValueChange={setTimeframe}>
            <TabsList className="bg-slate-800">
              <TabsTrigger value="1H">1H</TabsTrigger>
              <TabsTrigger value="24H">24H</TabsTrigger>
              <TabsTrigger value="7D">7D</TabsTrigger>
              <TabsTrigger value="30D">30D</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Checkbox
                checked={showComparison}
                onCheckedChange={(checked) => setShowComparison(Boolean(checked))}
                id="show-comparison"
              />
              <Label htmlFor="show-comparison" className="text-xs text-slate-300">Compare</Label>
            </div>
            <Select value={comparisonGPU} onValueChange={setComparisonGPU}>
              <SelectTrigger className="w-40 h-8 bg-slate-800 border-slate-700 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="RTX 3090">RTX 3090</SelectItem>
                <SelectItem value="RTX 4090">RTX 4090</SelectItem>
                <SelectItem value="A100">A100</SelectItem>
                <SelectItem value="H100">H100</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <Checkbox
                checked={showVolume}
                onCheckedChange={(checked) => setShowVolume(Boolean(checked))}
                id="show-volume"
              />
              <Label htmlFor="show-volume" className="text-xs text-slate-300">Volume overlay</Label>
            </div>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
            </linearGradient>
            <linearGradient id="colorReference" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.2}/>
              <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
            </linearGradient>
            <linearGradient id="colorVolume" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2}/>
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis 
            dataKey="time" 
            stroke="#94a3b8"
            tick={{ fill: '#94a3b8' }}
          />
          <YAxis 
            stroke="#94a3b8"
            tick={{ fill: '#94a3b8' }}
            domain={['auto', 'auto']}
          />
          <Tooltip 
            contentStyle={{ 
              backgroundColor: '#1e293b', 
              border: '1px solid #334155',
              borderRadius: '8px',
              color: '#f1f5f9'
            }}
          />
          <Area 
            type="monotone" 
            dataKey="price" 
            stroke="#3b82f6" 
            strokeWidth={2}
            fill="url(#colorPrice)" 
          />
          {showComparison && comparisonGPU !== selectedGPU ? (
            <Area
              type="monotone"
              dataKey="referencePrice"
              stroke="#f59e0b"
              strokeWidth={2}
              fill="url(#colorReference)"
            />
          ) : null}
          {showVolume ? (
            <Area
              type="monotone"
              dataKey="volumeScale"
              stroke="#22c55e"
              strokeWidth={1.5}
              fill="url(#colorVolume)"
            />
          ) : null}
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-slate-400">
        <span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-blue-500" />{selectedGPU}</span>
        {showComparison && comparisonGPU !== selectedGPU ? (
          <span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-amber-500" />{comparisonGPU}</span>
        ) : null}
        {showVolume ? (
          <span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-green-500" />Volume</span>
        ) : null}
      </div>
    </Card>
  );
}