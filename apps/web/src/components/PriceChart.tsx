import { Card } from './ui/card';
import { Tabs, TabsList, TabsTrigger } from './ui/tabs';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useState, useEffect } from 'react';
import { MarketApi } from '../lib/api';

interface PriceChartProps {
  selectedGPU: string;
}

type PricePoint = { time: string; price: number; volume: number };

export function PriceChart({ selectedGPU }: PriceChartProps) {
  const [data, setData] = useState<PricePoint[]>([]);
  const [timeframe, setTimeframe] = useState('24H');

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

  const currentPrice = data[data.length - 1]?.price || 0;
  const previousPrice = data[0]?.price || 0;
  const priceChange = currentPrice - previousPrice;
  const percentChange =
    previousPrice > 0 ? ((priceChange / previousPrice) * 100).toFixed(2) : '0.00';

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2>{selectedGPU}</h2>
          <div className="flex items-baseline gap-3 mt-2">
            <span className="text-3xl text-slate-100">${currentPrice.toFixed(2)}</span>
            <span className="text-sm text-slate-400">/hour</span>
            <span className={`text-sm ${parseFloat(percentChange) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {parseFloat(percentChange) >= 0 ? '+' : ''}{percentChange}%
            </span>
          </div>
        </div>
        <Tabs value={timeframe} onValueChange={setTimeframe}>
          <TabsList className="bg-slate-800">
            <TabsTrigger value="1H">1H</TabsTrigger>
            <TabsTrigger value="24H">24H</TabsTrigger>
            <TabsTrigger value="7D">7D</TabsTrigger>
            <TabsTrigger value="30D">30D</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
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
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}