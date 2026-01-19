import { useState, useEffect } from 'react';
import { MarketOverview } from './components/MarketOverview';
import { PriceChart } from './components/PriceChart';
import { GPUMarketplace } from './components/GPUMarketplace';
import { OrderBook } from './components/OrderBook';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Activity } from 'lucide-react';

export default function App() {
  const [selectedGPU, setSelectedGPU] = useState('RTX 4090');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-blue-600 p-2 rounded-lg">
                <Activity className="w-6 h-6" />
              </div>
              <div>
                <h1>GPU Compute Exchange</h1>
                <p className="text-slate-400 text-sm">Global GPU-Hour Marketplace</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-sm text-slate-400">Market Status</div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                  <span className="text-green-500">Live</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-6">
        {/* Market Overview */}
        <MarketOverview />

        {/* Main Trading Interface */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          {/* Left Column - Chart & Marketplace */}
          <div className="lg:col-span-2 space-y-6">
            <PriceChart selectedGPU={selectedGPU} />
            <GPUMarketplace onSelectGPU={setSelectedGPU} selectedGPU={selectedGPU} />
          </div>

          {/* Right Column - Order Book */}
          <div className="lg:col-span-1">
            <OrderBook selectedGPU={selectedGPU} />
          </div>
        </div>
      </div>
    </div>
  );
}


