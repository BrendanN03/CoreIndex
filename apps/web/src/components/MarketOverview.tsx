import { Card } from './ui/card';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { useEffect, useState } from 'react';

interface MarketStat {
  name: string;
  price: number;
  change: number;
  volume: string;
}

const initialStats: MarketStat[] = [
  { name: 'RTX 4090', price: 2.45, change: 5.2, volume: '1.2M' },
  { name: 'A100', price: 4.80, change: -2.1, volume: '890K' },
  { name: 'H100', price: 8.95, change: 12.3, volume: '2.4M' },
  { name: 'RTX 3090', price: 1.20, change: 3.5, volume: '650K' },
];

export function MarketOverview() {
  const [stats, setStats] = useState(initialStats);

  useEffect(() => {
    const interval = setInterval(() => {
      setStats(prev => prev.map(stat => ({
        ...stat,
        price: parseFloat((stat.price + (Math.random() - 0.5) * 0.1).toFixed(2)),
        change: parseFloat((stat.change + (Math.random() - 0.5) * 0.5).toFixed(1)),
      })));
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((stat, index) => (
        <Card key={index} className="bg-slate-900 border-slate-800 p-4 hover:border-slate-700 transition-colors">
          <div className="flex justify-between items-start mb-2">
            <div>
              <div className="text-slate-400 text-sm">{stat.name}</div>
              <div className="text-2xl text-slate-100">${stat.price}/hr</div>
            </div>
            <div className={`flex items-center gap-1 text-sm ${stat.change >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {stat.change >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              {Math.abs(stat.change)}%
            </div>
          </div>
          <div className="text-sm text-slate-400">
            Vol: {stat.volume} hrs
          </div>
        </Card>
      ))}
    </div>
  );
}