import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Input } from './ui/input';
import { Server, MapPin, Zap, TrendingUp, Search } from 'lucide-react';
import { useState } from 'react';

interface GPUListing {
  id: string;
  name: string;
  vram: string;
  location: string;
  region: string;
  price: number;
  availability: number;
  performance: string;
  change: number;
  provider: string;
}

const gpuListings: GPUListing[] = [
  {
    id: '1',
    name: 'RTX 4090',
    vram: '24GB',
    location: 'US-East',
    region: 'Virginia',
    price: 2.45,
    availability: 87,
    performance: '82.6 TFLOPS',
    change: 5.2,
    provider: 'AWS'
  },
  {
    id: '2',
    name: 'A100',
    vram: '80GB',
    location: 'US-West',
    region: 'Oregon',
    price: 4.80,
    availability: 34,
    performance: '312 TFLOPS',
    change: -2.1,
    provider: 'GCP'
  },
  {
    id: '3',
    name: 'H100',
    vram: '80GB',
    location: 'EU-Central',
    region: 'Frankfurt',
    price: 8.95,
    availability: 12,
    performance: '1000 TFLOPS',
    change: 12.3,
    provider: 'Azure'
  },
  {
    id: '4',
    name: 'RTX 3090',
    vram: '24GB',
    location: 'US-East',
    region: 'N. Virginia',
    price: 1.20,
    availability: 156,
    performance: '35.6 TFLOPS',
    change: 3.5,
    provider: 'Lambda'
  },
  {
    id: '5',
    name: 'RTX 4090',
    vram: '24GB',
    location: 'Asia-Pacific',
    region: 'Singapore',
    price: 2.65,
    availability: 45,
    performance: '82.6 TFLOPS',
    change: 4.8,
    provider: 'AWS'
  },
  {
    id: '6',
    name: 'A100',
    vram: '80GB',
    location: 'EU-West',
    region: 'Ireland',
    price: 4.95,
    availability: 28,
    performance: '312 TFLOPS',
    change: -1.5,
    provider: 'GCP'
  },
  {
    id: '7',
    name: 'RTX 3090',
    vram: '24GB',
    location: 'EU-Central',
    region: 'Frankfurt',
    price: 1.35,
    availability: 92,
    performance: '35.6 TFLOPS',
    change: 2.1,
    provider: 'Vast.ai'
  },
  {
    id: '8',
    name: 'H100',
    vram: '80GB',
    location: 'US-West',
    region: 'California',
    price: 9.20,
    availability: 8,
    performance: '1000 TFLOPS',
    change: 15.2,
    provider: 'Azure'
  },
];

interface GPUMarketplaceProps {
  onSelectGPU: (gpu: string) => void;
  selectedGPU: string;
}

export function GPUMarketplace({ onSelectGPU, selectedGPU }: GPUMarketplaceProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('price');

  const filteredListings = gpuListings
    .filter(gpu => 
      gpu.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      gpu.location.toLowerCase().includes(searchQuery.toLowerCase()) ||
      gpu.provider.toLowerCase().includes(searchQuery.toLowerCase())
    )
    .sort((a, b) => {
      if (sortBy === 'price') return a.price - b.price;
      if (sortBy === 'performance') return parseFloat(b.performance) - parseFloat(a.performance);
      if (sortBy === 'availability') return b.availability - a.availability;
      return 0;
    });

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-slate-100">Available GPU Compute</h2>
        <div className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input 
              placeholder="Search GPUs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-slate-800 border-slate-700 w-64"
            />
          </div>
        </div>
      </div>

      <Tabs defaultValue="all" className="mb-4">
        <TabsList className="bg-slate-800">
          <TabsTrigger value="all">All Regions</TabsTrigger>
          <TabsTrigger value="us">US</TabsTrigger>
          <TabsTrigger value="eu">EU</TabsTrigger>
          <TabsTrigger value="asia">Asia</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex gap-2 mb-4">
        <Button 
          variant={sortBy === 'price' ? 'default' : 'outline'} 
          size="sm"
          onClick={() => setSortBy('price')}
          className={sortBy !== 'price' ? 'bg-slate-800 border-slate-700' : ''}
        >
          Price
        </Button>
        <Button 
          variant={sortBy === 'performance' ? 'default' : 'outline'} 
          size="sm"
          onClick={() => setSortBy('performance')}
          className={sortBy !== 'performance' ? 'bg-slate-800 border-slate-700' : ''}
        >
          Performance
        </Button>
        <Button 
          variant={sortBy === 'availability' ? 'default' : 'outline'} 
          size="sm"
          onClick={() => setSortBy('availability')}
          className={sortBy !== 'availability' ? 'bg-slate-800 border-slate-700' : ''}
        >
          Availability
        </Button>
      </div>

      <div className="space-y-3 max-h-[600px] overflow-y-auto">
        {filteredListings.map((gpu) => (
          <div
            key={gpu.id}
            onClick={() => onSelectGPU(gpu.name)}
            className={`p-4 rounded-lg border transition-all cursor-pointer ${
              selectedGPU === gpu.name
                ? 'bg-blue-950/30 border-blue-700'
                : 'bg-slate-800/50 border-slate-700 hover:border-slate-600'
            }`}
          >
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-start gap-3">
                <div className="bg-slate-700 p-2 rounded">
                  <Server className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-100">{gpu.name}</span>
                    <Badge variant="outline" className="border-slate-600">
                      {gpu.vram}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-sm text-slate-400">
                    <div className="flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      {gpu.location} • {gpu.region}
                    </div>
                    <div className="flex items-center gap-1">
                      <Zap className="w-3 h-3" />
                      {gpu.performance}
                    </div>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-xl">${gpu.price}/hr</div>
                <div className={`text-sm flex items-center gap-1 justify-end ${
                  gpu.change >= 0 ? 'text-green-500' : 'text-red-500'
                }`}>
                  <TrendingUp className={`w-3 h-3 ${gpu.change < 0 ? 'rotate-180' : ''}`} />
                  {Math.abs(gpu.change)}%
                </div>
              </div>
            </div>

            <div className="flex justify-between items-center">
              <div className="flex items-center gap-4">
                <div>
                  <div className="text-xs text-slate-400">Provider</div>
                  <div className="text-sm text-slate-100">{gpu.provider}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400">Available</div>
                  <div className="text-sm text-slate-100">{gpu.availability} units</div>
                </div>
              </div>
              <Button 
                size="sm" 
                className="bg-blue-600 hover:bg-blue-700"
              >
                Connect
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}