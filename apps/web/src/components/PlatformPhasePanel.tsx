import { useEffect, useState } from 'react';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import {
  API_BASE_URL,
  MarketApi,
  PlatformApi,
  type MarketSimulationStatusResponseDto,
  type PlatformStatusResponseDto,
} from '../lib/api';

type Props = {
  signedIn: boolean;
  role?: 'buyer' | 'seller' | null;
};

export function PlatformPhasePanel({ signedIn, role }: Props) {
  const roleLabel = role === 'seller' ? 'provider' : role === 'buyer' ? 'buyer' : 'guest';
  const [platform, setPlatform] = useState<PlatformStatusResponseDto | null>(null);
  const [platformError, setPlatformError] = useState<string | null>(null);
  const [simStatus, setSimStatus] = useState<MarketSimulationStatusResponseDto | null>(null);
  const [simBusy, setSimBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadPlatformStatus() {
      try {
        const status = await PlatformApi.getStatus();
        if (!cancelled) {
          setPlatform(status);
          setPlatformError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setPlatform(null);
          setPlatformError(error instanceof Error ? error.message : String(error));
        }
      }
    }

    void loadPlatformStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function refreshSimulation() {
      try {
        const status = await MarketApi.getSimulationStatus();
        if (!cancelled) setSimStatus(status);
      } catch {
        if (!cancelled) setSimStatus(null);
      }
    }
    void refreshSimulation();
    const interval = setInterval(() => {
      void refreshSimulation();
    }, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <Card className="bg-slate-900 border-slate-800 p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-3">
          <div>
            <h2 className="text-slate-100">Platform Status</h2>
            <p className="mt-2 text-sm text-slate-400">
              Live system metadata and recent activity from the backend.
              {platform?.current_focus
                ? ` ${platform.current_focus}.`
                : ' Connecting to platform services.'}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:w-[480px]">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Viewer</div>
            <div className="mt-1 text-sm text-slate-100">{roleLabel}</div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Auth</div>
            <div className="mt-1 text-sm text-slate-100">{signedIn ? 'Active' : 'Waiting'}</div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">API</div>
            <div className="mt-1 truncate text-sm text-slate-100">{API_BASE_URL}</div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="text-sm text-slate-100">Execution</div>
          <div className="mt-2 space-y-1 text-sm text-slate-400">
            <div>Buyer and provider workspaces</div>
            <div>Job lifecycle with feasibility checks</div>
            <div>Nominations, lots, prepare, and result submission</div>
            <div>QC hashing and certificate verification</div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="text-sm text-slate-100">Market</div>
          <div className="mt-2 space-y-1 text-sm text-slate-400">
            <div>Product-key trading and settlement flow</div>
            <div>Voucher balances and job funding</div>
            <div>Order book and trade feed</div>
            <div>Position lifecycle</div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="text-sm text-slate-100">Infrastructure</div>
          <div className="mt-2 space-y-1 text-sm text-slate-400">
            <div>Persistent state and audit events</div>
            <div>Blockchain anchoring and settlement</div>
            <div>Risk and derivatives tooling</div>
            <div>Cross-machine collective networking</div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_1fr]">
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-100">Backend feed</div>
            <Badge variant="outline" className="border-slate-700 text-slate-200">
              {platform?.current_phase ?? 'offline'}
            </Badge>
          </div>

          {platformError ? (
            <div className="mt-3 text-sm text-red-200">{platformError}</div>
          ) : (
            <div className="mt-3 space-y-2 text-sm text-slate-400">
              <div>API version: {platform?.api_version ?? '...'}</div>
              <div>Recorded events: {platform?.event_count ?? 0}</div>
              <div className="flex flex-wrap gap-2 pt-1">
                {(platform?.capabilities ?? []).map((capability) => (
                  <Badge
                    key={capability}
                    variant="outline"
                    className="border-slate-800 text-slate-300"
                  >
                    {capability}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-100">Synthetic market simulation</div>
            <Badge
              variant="outline"
              className={simStatus?.running ? 'border-emerald-700 text-emerald-300' : 'border-slate-700 text-slate-300'}
            >
              {simStatus?.running ? 'running' : 'stopped'}
            </Badge>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-400">
            <div>Buy agents: {simStatus?.synthetic_buyer_agents ?? 0}</div>
            <div>Sell agents: {simStatus?.synthetic_seller_agents ?? 0}</div>
            <div>Ticks/sec: {simStatus?.ticks_per_second ?? 0}</div>
            <div>Total ticks: {simStatus?.total_ticks ?? 0}</div>
          </div>
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              className="bg-emerald-700 hover:bg-emerald-800"
              disabled={simBusy}
              onClick={async () => {
                setSimBusy(true);
                try {
                  const status = await MarketApi.startSimulation({
                    synthetic_buyer_agents: 60,
                    synthetic_seller_agents: 40,
                    ticks_per_second: 3,
                  });
                  setSimStatus(status);
                } finally {
                  setSimBusy(false);
                }
              }}
            >
              Start
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="bg-slate-800 border-slate-700"
              disabled={simBusy}
              onClick={async () => {
                setSimBusy(true);
                try {
                  const status = await MarketApi.stopSimulation();
                  setSimStatus(status);
                } finally {
                  setSimBusy(false);
                }
              }}
            >
              Stop
            </Button>
          </div>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="text-sm text-slate-100">Recent platform events</div>
          <div className="mt-3 space-y-2 text-sm text-slate-400">
            {platform?.recent_events?.length ? (
              platform.recent_events.map((event) => (
                <div key={event.event_id} className="rounded-md border border-slate-800 px-3 py-2">
                  <div className="text-slate-200">{event.event_type}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {event.entity_type} · {event.entity_id}
                  </div>
                </div>
              ))
            ) : (
              <div>No events yet. Create jobs or lots to see backend activity appear here.</div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
