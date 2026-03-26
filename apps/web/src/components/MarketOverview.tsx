import { Card } from './ui/card';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import { MarketApi, type MarketLiveOverviewRowDto } from '../lib/api';

export function MarketOverview() {
  const [stats, setStats] = useState<MarketLiveOverviewRowDto[]>([]);
  const [lastPrices, setLastPrices] = useState<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
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

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((stat) => (
        <Card
          key={stat.gpu_model}
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
            Bid: {stat.best_bid_per_ngh?.toFixed(2) ?? '--'} | Ask: {stat.best_ask_per_ngh?.toFixed(2) ?? '--'}
          </div>
        </Card>
      ))}
    </div>
  );
}