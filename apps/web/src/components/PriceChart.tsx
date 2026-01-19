import { Card } from './ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { useState, useEffect } from 'react';

interface PriceChartProps {
  selectedGPU: string;
}

const generateInitialData = (basePrice: number) => {
  const data = [];
  const now = new Date();
  for (let i = 23; i >= 0; i--) {
    const time = new Date(now.getTime() - i * 60 * 60 * 1000);
    data.push({
      time: time.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
      price: parseFloat((basePrice + Math.random() * 1 - 0.5).toFixed(2)),
      volume: Math.floor(Math.random() * 5000 + 10000),
    });
  }
  return data;
};

const basePrices: { [key: string]: number } = {
  'RTX 4090': 2.45,
  'A100': 4.80,
  'H100': 8.95,
  'RTX 3090': 1.20,
};

export function PriceChart({ selectedGPU }: PriceChartProps) {
  const [data, setData] = useState(generateInitialData(basePrices[selectedGPU] || 2.45));
  const [timeframe, setTimeframe] = useState('24H');

  useEffect(() => {
    setData(generateInitialData(basePrices[selectedGPU] || 2.45));
  }, [selectedGPU]);

  useEffect(() => {
    const interval = setInterval(() => {
      setData(prev => {
        const newData = [...prev.slice(1)];
        const lastPrice = prev[prev.length - 1].price;
        const now = new Date();
        newData.push({
          time: now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
          price: parseFloat((lastPrice + (Math.random() - 0.5) * 0.2).toFixed(2)),
          volume: Math.floor(Math.random() * 5000 + 10000),
        });
        return newData;
      });
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const currentPrice = data[data.length - 1]?.price || 0;
  const previousPrice = data[0]?.price || 0;
  const priceChange = currentPrice - previousPrice;
  const percentChange = ((priceChange / previousPrice) * 100).toFixed(2);

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