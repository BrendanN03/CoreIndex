import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Input } from './ui/input';
import { Server, MapPin, Zap, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  JobApi,
  ProviderApi,
  type JobCreateRequestDto,
  type MarketplaceGpuListingResponseDto,
} from '../lib/api';

interface GPUMarketplaceProps {
  onSelectGPU: (gpu: string) => void;
  selectedGPU: string;
  /** Called after a job is successfully created (e.g. to refresh My Jobs). */
  onJobCreated?: () => void;
}

export function GPUMarketplace({ onSelectGPU, selectedGPU, onJobCreated }: GPUMarketplaceProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [regionFilter, setRegionFilter] = useState<'all' | 'us' | 'eu' | 'asia'>('all');
  const [sortBy, setSortBy] = useState<'price' | 'availability'>('price');
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
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
          row.provider_id.toLowerCase().includes(q) ||
          row.region.toLowerCase().includes(q),
      )
      .sort((a, b) => {
        if (sortBy === 'price') return a.indicative_price_per_ngh - b.indicative_price_per_ngh;
        return b.ngh_available - a.ngh_available;
      });
  }, [listings, searchQuery, regionFilter, sortBy]);

  async function handleConnectClick(gpu: MarketplaceGpuListingResponseDto) {
    onSelectGPU(gpu.gpu_model);
    setStatus(null);
    setError(null);
    setIsCreating(true);

    try {
      const now = new Date();
      const utcHour = now.getUTCHours();

      const body: JobCreateRequestDto = {
        job_id: `job-${Date.now()}`,
        window: {
          region: gpu.region,
          iso_hour: gpu.iso_hour ?? utcHour,
          sla: gpu.sla,
          tier: gpu.tier,
        },
        package_index: [
          {
            package_id: `pkg-${Date.now()}`,
            size_estimate_ngh: Math.max(1, Math.min(10, gpu.ngh_available)),
            first_output_estimate_seconds: 60,
            metadata: {
              gpu_name: gpu.gpu_model,
              provider: gpu.provider_id,
              listing_id: gpu.listing_id,
            },
          },
        ],
      };

      await JobApi.createJob(body);
      const feas = await JobApi.getFeasibility(body.job_id);

      setStatus(
        `Created job ${body.job_id}: NGH=${feas.ngh_required.toFixed(
          2,
        )}, voucher_gap=${feas.voucher_gap.toFixed(2)}, ` +
          `first_output_ok=${feas.milestone_sanity.first_output_ok ? 'yes' : 'no'}, ` +
          `size_band_ok=${feas.milestone_sanity.size_band_ok ? 'yes' : 'no'}`,
      );
      onJobCreated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus('Failed to create job from selected provider listing.');
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-slate-100">Available GPU Compute (Live Seller Listings)</h2>
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
              <Button
                size="sm"
                className="bg-blue-600 hover:bg-blue-700"
                onClick={(e) => {
                  e.stopPropagation();
                  void handleConnectClick(gpu);
                }}
                disabled={isCreating}
              >
                {isCreating ? 'Connecting...' : 'Connect'}
              </Button>
            </div>
          </div>
        ))}
      </div>
      {status && (
        <div className="mt-4 text-xs text-slate-300 border-t border-slate-800 pt-3">
          {status}
        </div>
      )}
    </Card>
  );
}