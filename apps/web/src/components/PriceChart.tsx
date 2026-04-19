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

const GPU_MODELS = ['RTX 3090', 'RTX 4090', 'A100', 'H100'] as const;

/** Polling + points cap: ~3s × 120 ≈ 6 minutes of live history in demo. */
const POLL_MS = 1800;
const MAX_POINTS = 140;

type ChartRow = {
  t: number;
  time: string;
  price: number;
  volume: number;
  referencePrice?: number;
};

function formatClock(ms: number): string {
  return new Date(ms).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function midFromBook(book: {
  best_bid?: number | null;
  best_ask?: number | null;
}): number | null {
  const bid = book.best_bid ?? null;
  const ask = book.best_ask ?? null;
  if (bid != null && ask != null) {
    return (bid + ask) / 2;
  }
  if (bid != null) return bid;
  if (ask != null) return ask;
  return null;
}

export function PriceChart({ selectedGPU }: PriceChartProps) {
  /** Primary series — user can override vs marketplace GPU selection. */
  const [chartGpu, setChartGpu] = useState(selectedGPU);
  const [data, setData] = useState<ChartRow[]>([]);
  const [timeframe, setTimeframe] = useState('24H');
  const [comparisonGPU, setComparisonGPU] = useState('A100');
  const [showComparison, setShowComparison] = useState(true);
  const [showVolume, setShowVolume] = useState(false);

  useEffect(() => {
    setChartGpu(selectedGPU);
  }, [selectedGPU]);

  useEffect(() => {
    let cancelled = false;
    setData([]);

    async function poll() {
      try {
        const [tapeP, bookP] = await Promise.all([
          MarketApi.getLiveTape({ gpu_model: chartGpu, limit: 80 }),
          MarketApi.getLiveOrderBook({ gpu_model: chartGpu }),
        ]);
        if (cancelled) return;

        let midP = midFromBook(bookP);
        if (midP == null && tapeP.length > 0) {
          midP = tapeP[0].price_per_ngh;
        }
        if (midP == null || !Number.isFinite(midP) || midP <= 0) return;

        let refPx: number | undefined;
        if (showComparison && comparisonGPU !== chartGpu) {
          const [tapeC, bookC] = await Promise.all([
            MarketApi.getLiveTape({ gpu_model: comparisonGPU, limit: 80 }),
            MarketApi.getLiveOrderBook({ gpu_model: comparisonGPU }),
          ]);
          if (cancelled) return;
          let midC = midFromBook(bookC);
          if (midC == null && tapeC.length > 0) {
            midC = tapeC[0].price_per_ngh;
          }
          if (midC != null && Number.isFinite(midC) && midC > 0) {
            refPx = Number(midC.toFixed(4));
          }
        }

        const t = Date.now();
        const row: ChartRow = {
          t,
          time: formatClock(t),
          price: Number(midP.toFixed(4)),
          volume: tapeP.length ? tapeP[0].quantity_ngh : 0,
        };
        if (refPx != null) row.referencePrice = refPx;

        setData((prev) => {
          if (prev.length === 0 && tapeP.length > 0) {
            const hist = [...tapeP]
              .reverse()
              .map((tr) => {
                const ts = Date.parse(tr.created_at);
                const safe = Number.isFinite(ts) ? ts : t;
                return {
                  t: safe,
                  time: formatClock(safe),
                  price: Number(tr.price_per_ngh.toFixed(4)),
                  volume: tr.quantity_ngh,
                } satisfies ChartRow;
              })
              .filter((p) => p.price > 0);
            return [...hist, row].slice(-MAX_POINTS);
          }
          return [...prev, row].slice(-MAX_POINTS);
        });
      } catch {
        /* keep series */
      }
    }

    void poll();
    const interval = globalThis.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      globalThis.clearInterval(interval);
    };
  }, [chartGpu, comparisonGPU, showComparison]);

  const windowed = useMemo(() => {
    const limits: Record<string, number> = {
      '1H': 45,
      '24H': 90,
      '7D': MAX_POINTS,
      '30D': MAX_POINTS,
    };
    const n = limits[timeframe] ?? 90;
    return data.slice(-n);
  }, [data, timeframe]);

  const chartData = useMemo(() => {
    if (!showVolume) return windowed;
    return windowed.map((point) => ({ ...point, volumeScale: point.volume }));
  }, [windowed, showVolume]);

  const currentPrice = windowed[windowed.length - 1]?.price || 0;
  const previousPrice = windowed[0]?.price || 0;
  const priceChange = currentPrice - previousPrice;
  const percentChange =
    previousPrice > 0 ? ((priceChange / previousPrice) * 100).toFixed(2) : '0.00';
  const comparisonCurrentPrice = windowed[windowed.length - 1]?.referencePrice ?? 0;

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex flex-col gap-4 justify-between lg:flex-row lg:items-start mb-6">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg text-slate-100">Price chart</h2>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="hidden sm:inline">Primary</span>
              <Select value={chartGpu} onValueChange={setChartGpu}>
                <SelectTrigger className="h-8 w-[9.5rem] bg-slate-800 border-slate-700 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {GPU_MODELS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-slate-500">(syncs from desk GPU; override here)</span>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-baseline gap-3">
            <span className="text-3xl text-slate-100">${currentPrice.toFixed(2)}</span>
            <span className="text-sm text-slate-400">/NGH</span>
            <span className={`text-sm ${parseFloat(percentChange) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {parseFloat(percentChange) >= 0 ? '+' : ''}
              {percentChange}%
            </span>
            <span className="text-xs text-slate-500">over visible window</span>
          </div>
          {showComparison && comparisonGPU !== chartGpu && comparisonCurrentPrice > 0 ? (
            <div className="mt-1 text-xs text-slate-400">
              Comparison: {comparisonGPU} ${comparisonCurrentPrice.toFixed(2)} /NGH (same time axis)
            </div>
          ) : null}
        </div>
        <div className="space-y-3 shrink-0">
          <Tabs value={timeframe} onValueChange={setTimeframe}>
            <TabsList className="bg-slate-800">
              <TabsTrigger value="1H">1H</TabsTrigger>
              <TabsTrigger value="24H">24H</TabsTrigger>
              <TabsTrigger value="7D">7D</TabsTrigger>
              <TabsTrigger value="30D">30D</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Checkbox
                checked={showComparison}
                onCheckedChange={(checked) => setShowComparison(Boolean(checked))}
                id="show-comparison"
              />
              <Label htmlFor="show-comparison" className="text-xs text-slate-300">
                Compare
              </Label>
            </div>
            <Select value={comparisonGPU} onValueChange={setComparisonGPU}>
              <SelectTrigger className="w-40 h-8 bg-slate-800 border-slate-700 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GPU_MODELS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <Checkbox
                checked={showVolume}
                onCheckedChange={(checked) => setShowVolume(Boolean(checked))}
                id="show-volume"
              />
              <Label htmlFor="show-volume" className="text-xs text-slate-300">
                Volume overlay
              </Label>
            </div>
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="colorReference" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="colorVolume" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            stroke="#94a3b8"
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            tickFormatter={(v) => formatClock(Number(v))}
          />
          <YAxis
            stroke="#94a3b8"
            tick={{ fill: '#94a3b8' }}
            domain={['auto', 'auto']}
            tickFormatter={(v) => `$${v}`}
          />
          <Tooltip
            labelFormatter={(v) => formatClock(Number(v))}
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '8px',
              color: '#f1f5f9',
            }}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="url(#colorPrice)"
            isAnimationActive={false}
          />
          {showComparison && comparisonGPU !== chartGpu ? (
            <Area
              type="monotone"
              dataKey="referencePrice"
              stroke="#f59e0b"
              strokeWidth={2}
              fill="url(#colorReference)"
              connectNulls
              isAnimationActive={false}
            />
          ) : null}
          {showVolume ? (
            <Area
              type="monotone"
              dataKey="volumeScale"
              stroke="#22c55e"
              strokeWidth={1.5}
              fill="url(#colorVolume)"
              isAnimationActive={false}
            />
          ) : null}
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-slate-400">
        <span className="inline-flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-blue-500" />
          {chartGpu}
        </span>
        {showComparison && comparisonGPU !== chartGpu ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            {comparisonGPU}
          </span>
        ) : null}
        {showVolume ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            Volume
          </span>
        ) : null}
      </div>
    </Card>
  );
}
