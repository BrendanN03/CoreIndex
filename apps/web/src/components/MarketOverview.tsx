import { Card } from './ui/card';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { MarketApi, type MarketLiveOverviewRowDto } from '../lib/api';

export function MarketOverview() {
  const [stats, setStats] = useState<MarketLiveOverviewRowDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastPrices, setLastPrices] = useState<Record<string, number>>({});
  const [sortBy, setSortBy] = useState<'price' | 'volume' | 'spread' | 'orders'>('volume');

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      setLoading(true);
      try {
        const response = await MarketApi.getLiveOverview();
        if (cancelled) return;
        setLastPrices((previous) => {
          const next = { ...previous };
          response.rows.forEach((row) => {
            if (next[row.gpu_model] === undefined) {
              next[row.gpu_model] = row.last_price_per_ngh;
            }
          });
          return next;
        });
        setStats(response.rows);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void refresh().catch(() => undefined);
    const interval = setInterval(() => {
      void refresh().catch(() => undefined);
    }, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const sortedStats = useMemo(() => {
    const rows = [...stats];
    rows.sort((a, b) => {
      if (sortBy === 'price') return b.last_price_per_ngh - a.last_price_per_ngh;
      if (sortBy === 'orders') return b.active_order_count - a.active_order_count;
      if (sortBy === 'spread') return (b.spread_per_ngh ?? 0) - (a.spread_per_ngh ?? 0);
      return b.traded_volume_ngh_5m - a.traded_volume_ngh_5m;
    });
    return rows;
  }, [sortBy, stats]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-slate-400">
          {loading ? 'Refreshing market data...' : 'Live product-level market snapshot across all available compute tiers'}
        </div>
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as typeof sortBy)}>
          <SelectTrigger className="w-56 bg-slate-800 border-slate-700">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="volume">Sort by 5m volume</SelectItem>
            <SelectItem value="price">Sort by last price</SelectItem>
            <SelectItem value="spread">Sort by spread</SelectItem>
            <SelectItem value="orders">Sort by active orders</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {sortedStats.map((stat) => (
        <Card
          key={
            stat.gpu_model +
            stat.product_key.region +
            stat.product_key.tier +
            stat.product_key.iso_hour
          }
          className="bg-slate-900 border-slate-800 p-4 hover:border-slate-700 transition-colors"
        >
          {(() => {
            const previous = lastPrices[stat.gpu_model] ?? stat.last_price_per_ngh;
            const changePct = previous > 0 ? ((stat.last_price_per_ngh - previous) / previous) * 100 : 0;
            const positive = changePct >= 0;
            return (
          <div className="flex justify-between items-start mb-2">
            <div>
              <div className="text-slate-400 text-sm">{stat.gpu_model}</div>
              <div className="text-2xl text-slate-100">${stat.last_price_per_ngh.toFixed(2)}/NGH</div>
            </div>
            <div className={`flex items-center gap-1 text-sm ${positive ? 'text-green-500' : 'text-red-500'}`}>
              {positive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              {Math.abs(changePct).toFixed(2)}%
            </div>
          </div>
            );
          })()}
          <div className="text-sm text-slate-400">
            Vol(5m): {stat.traded_volume_ngh_5m.toFixed(2)} NGH
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {stat.product_key.region} · {stat.product_key.iso_hour}h · {stat.product_key.sla} ·{' '}
            {stat.product_key.tier}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            Bid: {stat.best_bid_per_ngh?.toFixed(2) ?? '--'} | Ask: {stat.best_ask_per_ngh?.toFixed(2) ?? '--'}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            Spread: {stat.spread_per_ngh != null ? stat.spread_per_ngh.toFixed(2) : '--'} · Orders: {stat.active_order_count}
          </div>
        </Card>
      ))}
      </div>
    </div>
  );
}