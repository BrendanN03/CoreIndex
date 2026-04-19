import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Input } from './ui/input';
import { Server, MapPin, Zap, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  ProviderApi,
  type MarketplaceGpuListingResponseDto,
} from '../lib/api';

interface GPUMarketplaceProps {
  onSelectGPU: (gpu: string) => void;
  selectedGPU: string;
}

export function GPUMarketplace({ onSelectGPU, selectedGPU }: GPUMarketplaceProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [regionFilter, setRegionFilter] = useState<'all' | 'us' | 'eu' | 'asia'>('all');
  const [sortBy, setSortBy] = useState<'price' | 'availability'>('price');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [listings, setListings] = useState<MarketplaceGpuListingResponseDto[]>([]);

  async function refreshListings() {
    setIsLoading(true);
    setError(null);
    const delays = [0, 80, 200, 450];
    for (let attempt = 0; attempt < delays.length; attempt++) {
      if (delays[attempt] > 0) {
        await new Promise((r) => setTimeout(r, delays[attempt]));
      }
      try {
        const rows = await ProviderApi.getListings();
        setListings(rows);
        setError(null);
        setIsLoading(false);
        return;
      } catch (err) {
        if (attempt === delays.length - 1) {
          setError(err instanceof Error ? err.message : String(err));
          setListings([]);
        }
      }
    }
    setIsLoading(false);
  }

  useEffect(() => {
    void refreshListings();
  }, []);

  const filteredListings = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const regionMatches = (row: MarketplaceGpuListingResponseDto) => {
      if (regionFilter === 'all') return true;
      if (regionFilter === 'us') return row.region.startsWith('us-');
      if (regionFilter === 'eu') return row.region.startsWith('eu-');
      return row.region.startsWith('asia-');
    };
    return listings
      .filter((row) => regionMatches(row))
      .filter(
        (row) =>
          !q ||
          row.gpu_model.toLowerCase().includes(q) ||
          row.region.toLowerCase().includes(q),
      )
      .sort((a, b) => {
        if (sortBy === 'price') return a.indicative_price_per_ngh - b.indicative_price_per_ngh;
        return b.ngh_available - a.ngh_available;
      });
  }, [listings, searchQuery, regionFilter, sortBy]);

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-slate-100">Live Seller Liquidity (Market-assigned at execution)</h2>
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
          <Button
            variant="outline"
            className="bg-slate-800 border-slate-700"
            onClick={() => void refreshListings()}
            disabled={isLoading}
          >
            {isLoading ? 'Refreshing...' : 'Refresh'}
          </Button>
        </div>
      </div>
      <p className="mb-4 text-xs text-slate-400">
        Listings are indicative supply for each compute class. Buyers do not bind to a specific seller here:
        matching is market-assigned during execution using price, capacity, and reliability.
      </p>

      <Tabs value={regionFilter} onValueChange={(v) => setRegionFilter(v as 'all' | 'us' | 'eu' | 'asia')} className="mb-4">
        <TabsList className="bg-slate-800">
          <TabsTrigger value="all">All Regions</TabsTrigger>
          <TabsTrigger value="us">US</TabsTrigger>
          <TabsTrigger value="eu">EU</TabsTrigger>
          <TabsTrigger value="asia">Asia</TabsTrigger>
        </TabsList>
        <TabsContent value={regionFilter} />
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
          variant={sortBy === 'availability' ? 'default' : 'outline'} 
          size="sm"
          onClick={() => setSortBy('availability')}
          className={sortBy !== 'availability' ? 'bg-slate-800 border-slate-700' : ''}
        >
          Availability
        </Button>
      </div>

      <div className="space-y-3 max-h-[min(22rem,45vh)] overflow-y-auto overscroll-contain pr-1">
        {error ? (
          <div className="rounded-lg border border-red-900/40 bg-red-950/30 p-3 text-sm text-red-200">
            {error}
          </div>
        ) : null}
        {!isLoading && filteredListings.length === 0 ? (
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
            No seller listings yet. Ask provider accounts to submit nominations first.
          </div>
        ) : null}
        {filteredListings.map((gpu) => (
          <div
            key={gpu.listing_id}
            onClick={() => onSelectGPU(gpu.gpu_model)}
            className={`p-4 rounded-lg border transition-all cursor-pointer ${
              selectedGPU === gpu.gpu_model
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
                    <span className="text-slate-100">{gpu.gpu_model}</span>
                    <Badge variant="outline" className="border-slate-600">
                      {gpu.gpu_count} GPU
                    </Badge>
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-sm text-slate-400">
                    <div className="flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      {gpu.region} • {gpu.iso_hour}h • {gpu.sla}
                    </div>
                    <div className="flex items-center gap-1">
                      <Zap className="w-3 h-3" />
                      {gpu.ngh_available.toFixed(2)} NGH
                    </div>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-xl">${gpu.indicative_price_per_ngh.toFixed(2)}/NGH</div>
                <div className="text-xs text-slate-500">{gpu.created_at}</div>
              </div>
            </div>

            <div className="flex justify-between items-center">
              <div className="flex items-center gap-4">
                <div>
                  <div className="text-xs text-slate-400">Provider</div>
                  <div className="text-sm text-slate-100">{gpu.provider_id}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400">Available</div>
                  <div className="text-sm text-slate-100">{gpu.ngh_available.toFixed(2)} NGH</div>
                </div>
              </div>
              <Badge variant="outline" className="border-slate-700 text-slate-300">
                Market-assigned
              </Badge>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}