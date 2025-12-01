import { Card } from './ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';

interface OrderBookProps {
  selectedGPU: string;
}

interface Order {
  price: number;
  hours: number;
  total: number;
}

const generateOrders = (basePrice: number, isBuy: boolean): Order[] => {
  const orders: Order[] = [];
  for (let i = 0; i < 8; i++) {
    const priceOffset = isBuy ? -0.05 * (i + 1) : 0.05 * (i + 1);
    const price = parseFloat((basePrice + priceOffset).toFixed(2));
    const hours = Math.floor(Math.random() * 500 + 100);
    orders.push({
      price,
      hours,
      total: parseFloat((price * hours).toFixed(2))
    });
  }
  return orders;
};

const basePrices: { [key: string]: number } = {
  'RTX 4090': 2.45,
  'A100': 4.80,
  'H100': 8.95,
  'RTX 3090': 1.20,
};

export function OrderBook({ selectedGPU }: OrderBookProps) {
  const basePrice = basePrices[selectedGPU] || 2.45;
  const [buyOrders, setBuyOrders] = useState(generateOrders(basePrice, true));
  const [sellOrders, setSellOrders] = useState(generateOrders(basePrice, false));
  const [hours, setHours] = useState('100');
  const [price, setPrice] = useState(basePrice.toString());

  useEffect(() => {
    const newBasePrice = basePrices[selectedGPU] || 2.45;
    setBuyOrders(generateOrders(newBasePrice, true));
    setSellOrders(generateOrders(newBasePrice, false));
    setPrice(newBasePrice.toString());
  }, [selectedGPU]);

  useEffect(() => {
    const interval = setInterval(() => {
      setBuyOrders(generateOrders(parseFloat(price), true));
      setSellOrders(generateOrders(parseFloat(price), false));
    }, 5000);
    return () => clearInterval(interval);
  }, [price]);

  return (
    <div className="space-y-6">
      {/* Order Book */}
      <Card className="bg-slate-900 border-slate-800 p-6">
        <h3 className="mb-4 text-slate-100">Order Book</h3>
        
        {/* Sell Orders */}
        <div className="mb-4">
          <div className="grid grid-cols-3 gap-2 text-xs text-slate-400 mb-2 px-2">
            <div>Price ($/hr)</div>
            <div className="text-right">Hours</div>
            <div className="text-right">Total ($)</div>
          </div>
          <div className="space-y-1">
            {sellOrders.reverse().map((order, i) => (
              <div 
                key={`sell-${i}`}
                className="grid grid-cols-3 gap-2 text-sm p-2 rounded hover:bg-slate-800/50 cursor-pointer relative overflow-hidden"
              >
                <div 
                  className="absolute right-0 top-0 bottom-0 bg-red-950/20"
                  style={{ width: `${(order.hours / 600) * 100}%` }}
                />
                <div className="text-red-400 relative z-10">{order.price.toFixed(2)}</div>
                <div className="text-right text-slate-100 relative z-10">{order.hours}</div>
                <div className="text-right text-slate-100 relative z-10">{order.total.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Current Price */}
        <div className="py-3 px-2 bg-slate-800 rounded-lg mb-4 text-center">
          <div className="text-2xl text-green-400">${basePrice.toFixed(2)}</div>
          <div className="text-xs text-slate-400">Current Market Price</div>
        </div>

        {/* Buy Orders */}
        <div>
          <div className="space-y-1">
            {buyOrders.map((order, i) => (
              <div 
                key={`buy-${i}`}
                className="grid grid-cols-3 gap-2 text-sm p-2 rounded hover:bg-slate-800/50 cursor-pointer relative overflow-hidden"
              >
                <div 
                  className="absolute right-0 top-0 bottom-0 bg-green-950/20"
                  style={{ width: `${(order.hours / 600) * 100}%` }}
                />
                <div className="text-green-400 relative z-10">{order.price.toFixed(2)}</div>
                <div className="text-right text-slate-100 relative z-10">{order.hours}</div>
                <div className="text-right text-slate-100 relative z-10">{order.total.toFixed(2)}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Trading Panel */}
      <Card className="bg-slate-900 border-slate-800 p-6">
        <Tabs defaultValue="buy">
          <TabsList className="w-full bg-slate-800">
            <TabsTrigger value="buy" className="flex-1">Buy</TabsTrigger>
            <TabsTrigger value="sell" className="flex-1">Sell</TabsTrigger>
          </TabsList>
          
          <TabsContent value="buy" className="space-y-4 mt-4">
            <div>
              <Label>Price ($/hour)</Label>
              <Input 
                type="number" 
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="bg-slate-800 border-slate-700 mt-1"
                step="0.01"
              />
            </div>
            <div>
              <Label>Compute Hours</Label>
              <Input 
                type="number" 
                value={hours}
                onChange={(e) => setHours(e.target.value)}
                className="bg-slate-800 border-slate-700 mt-1"
              />
            </div>
            <div className="p-3 bg-slate-800 rounded-lg">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-400">Total Cost</span>
                <span className="text-slate-100">${(parseFloat(price) * parseFloat(hours || '0')).toFixed(2)}</span>
              </div>
            </div>
            <Button className="w-full bg-green-600 hover:bg-green-700">
              Buy Compute Hours
            </Button>
          </TabsContent>

          <TabsContent value="sell" className="space-y-4 mt-4">
            <div>
              <Label>Price ($/hour)</Label>
              <Input 
                type="number" 
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="bg-slate-800 border-slate-700 mt-1"
                step="0.01"
              />
            </div>
            <div>
              <Label>Compute Hours</Label>
              <Input 
                type="number" 
                value={hours}
                onChange={(e) => setHours(e.target.value)}
                className="bg-slate-800 border-slate-700 mt-1"
              />
            </div>
            <div className="p-3 bg-slate-800 rounded-lg">
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-400">Total Revenue</span>
                <span className="text-slate-100">${(parseFloat(price) * parseFloat(hours || '0')).toFixed(2)}</span>
              </div>
            </div>
            <Button className="w-full bg-red-600 hover:bg-red-700">
              Sell Compute Hours
            </Button>
          </TabsContent>
        </Tabs>
      </Card>

      {/* Recent Trades */}
      <Card className="bg-slate-900 border-slate-800 p-6">
        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-4 h-4" />
          <h3 className="text-slate-100">Recent Trades</h3>
        </div>
        <div className="space-y-2">
          {[
            { price: 2.45, hours: 250, time: '10:23:45', type: 'buy' },
            { price: 2.44, hours: 180, time: '10:22:12', type: 'sell' },
            { price: 2.46, hours: 320, time: '10:21:38', type: 'buy' },
            { price: 2.43, hours: 150, time: '10:20:05', type: 'sell' },
            { price: 2.45, hours: 200, time: '10:19:22', type: 'buy' },
          ].map((trade, i) => (
            <div key={i} className="flex justify-between text-sm p-2 hover:bg-slate-800/50 rounded">
              <span className={trade.type === 'buy' ? 'text-green-400' : 'text-red-400'}>
                ${trade.price}
              </span>
              <span className="text-slate-400">{trade.hours}h</span>
              <span className="text-slate-500">{trade.time}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}