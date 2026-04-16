import { useEffect, useState } from 'react';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import {
  API_BASE_URL,
  MarketApi,
  PlatformApi,
  QcApi,
  type GpuBackendStatusDto,
  type MarketSimulationStatusResponseDto,
  type PlatformStatusResponseDto,
  type QcGoldCorpusSavedReportDto,
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
  const [gpuBackend, setGpuBackend] = useState<GpuBackendStatusDto | null>(null);
  const [latestGoldReport, setLatestGoldReport] = useState<QcGoldCorpusSavedReportDto | null>(null);
  const [simBusy, setSimBusy] = useState(false);
  const [presentationBusy, setPresentationBusy] = useState(false);
  const [simBuyerAgents, setSimBuyerAgents] = useState(240);
  const [simSellerAgents, setSimSellerAgents] = useState(180);
  const [simTicksPerSecond, setSimTicksPerSecond] = useState(4);

  useEffect(() => {
    let cancelled = false;

    async function loadPlatformStatus() {
      const delays = [0, 80, 200, 450];
      for (let i = 0; i < delays.length; i++) {
        if (delays[i] > 0) {
          await new Promise((r) => setTimeout(r, delays[i]));
        }
        if (cancelled) return;
        try {
          const status = await PlatformApi.getStatus();
          if (!cancelled) {
            setPlatform(status);
            setPlatformError(null);
          }
          return;
        } catch (error) {
          if (cancelled) return;
          if (i === delays.length - 1) {
            setPlatform(null);
            setPlatformError(error instanceof Error ? error.message : String(error));
          }
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
    async function loadPresentationSignals() {
      try {
        const [gpu, reports] = await Promise.all([
          PlatformApi.getGpuBackend(),
          QcApi.listGoldCorpusReports(1),
        ]);
        if (cancelled) return;
        setGpuBackend(gpu);
        setLatestGoldReport(reports.reports[0] ?? null);
      } catch {
        if (cancelled) return;
        setGpuBackend(null);
        setLatestGoldReport(null);
      }
    }
    void loadPresentationSignals();
    return () => {
      cancelled = true;
    };
  }, []);

  const checks = [
    { label: 'Auth active', pass: signedIn },
    { label: 'API connected', pass: !platformError && !!platform },
    { label: 'GPU path reachable', pass: gpuBackend?.tcp_reachable === true },
    { label: 'Market engine running', pass: simStatus?.running === true },
    { label: 'Latest P2 benchmark pass', pass: latestGoldReport?.pass_criteria_met === true },
  ];
  const overallReady = checks.every((row) => row.pass);

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
    async function ensureSimulationRunning() {
      try {
        const st = await MarketApi.getSimulationStatus();
        if (cancelled || st.running) return;
        await MarketApi.startSimulation({
          synthetic_buyer_agents: 30,
          synthetic_seller_agents: 20,
          ticks_per_second: 2,
        });
        if (!cancelled) {
          const next = await MarketApi.getSimulationStatus();
          setSimStatus(next);
        }
      } catch {
        /* API may be booting — periodic refresh will retry */
      }
    }
    void refreshSimulation().then(() => {
      if (!cancelled) void ensureSimulationRunning();
    });
    const interval = setInterval(() => {
      void refreshSimulation();
    }, 8000);
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
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 xl:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm text-slate-100">Presentation command center (P3)</div>
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={overallReady ? 'border-emerald-700 text-emerald-300' : 'border-amber-700 text-amber-300'}
              >
                {overallReady ? 'ready to present' : 'needs checks'}
              </Badge>
              <Button
                size="sm"
                variant="outline"
                className="bg-slate-800 border-slate-700"
                disabled={presentationBusy}
                onClick={async () => {
                  setPresentationBusy(true);
                  try {
                    const [status, sim, gpu, reports] = await Promise.all([
                      PlatformApi.getStatus(),
                      MarketApi.getSimulationStatus(),
                      PlatformApi.getGpuBackend(),
                      QcApi.listGoldCorpusReports(1),
                    ]);
                    setPlatform(status);
                    setSimStatus(sim);
                    setGpuBackend(gpu);
                    setLatestGoldReport(reports.reports[0] ?? null);
                    setPlatformError(null);
                  } catch (e) {
                    setPlatformError(e instanceof Error ? e.message : String(e));
                  } finally {
                    setPresentationBusy(false);
                  }
                }}
              >
                {presentationBusy ? 'Refreshing…' : 'Refresh checks'}
              </Button>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-5">
            {checks.map((row) => (
              <div key={row.label} className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-2 text-xs">
                <div className="text-slate-400">{row.label}</div>
                <div className={row.pass ? 'text-emerald-300' : 'text-amber-300'}>
                  {row.pass ? 'PASS' : 'FAIL'}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
            <div className="text-slate-200">Presentation script</div>
            <div className="mt-1 space-y-1 text-slate-400">
              <div>1) Buyer locks compute exposure (futures desk) and verifies voucher balances.</div>
              <div>2) Launch job execution and show provider lot split plus signed execution receipts.</div>
              <div>3) Open QC panel and run presentation check (matrix + adversarial + gold corpus).</div>
              <div>4) Anchor settlement and run on-chain verification for transparent proof.</div>
              <div>5) Close with saved benchmark history and latest platform events.</div>
            </div>
          </div>
          <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
            <div className="text-slate-200">End-to-end CoreIndex timeline</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {[
                'Buyer selects delivery window',
                'Buyer locks vouchers',
                'Providers submit signed capacity',
                'Matcher assigns lots',
                'Lots run on GPUs',
                'Verifier checks sampled work',
                'Receipt root anchored on-chain',
                'Accepted providers paid',
              ].map((step) => (
                <Badge key={step} variant="outline" className="border-slate-700 text-slate-300">
                  {step}
                </Badge>
              ))}
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
            <div className="rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
              <div className="text-slate-200">Market-based matching</div>
              <div className="mt-1 space-y-1 text-slate-400">
                <div>Standardized products: region, delivery hour, SLA, and hardware tier.</div>
                <div>Buyer bids and provider asks are matched by price-time priority.</div>
                <div>Reliability and available GPU inventory are applied as execution guards.</div>
                <div>Only accepted delivery contributes to benchmark settlement and payout.</div>
              </div>
            </div>
            <div className="rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
              <div className="text-slate-200">CADO-NFS benchmark</div>
              <div className="mt-1 space-y-1 text-slate-400">
                <div>CADO-NFS is used as a realistic, split-able multi-GPU workload.</div>
                <div>Lots run across providers and return signed execution receipts.</div>
                <div>QC compares canonicalized outputs to catch divergence early.</div>
                <div>Settlement releases payment only for verified accepted lots.</div>
              </div>
            </div>
          </div>
          <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
            <div className="text-slate-200">On-chain verification flow</div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              {[
                'Voucher escrow',
                'Provider signed receipts',
                'Verifier checks sampled lots',
                'Accepted receipts -> receipt root',
                'Root committed on-chain',
                'Debit vouchers + pay accepted providers',
                'Buyer receives output + proof',
              ].map((step) => (
                <Badge key={step} variant="outline" className="border-slate-700 text-slate-300">
                  {step}
                </Badge>
              ))}
            </div>
          </div>
          <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
            <div className="text-slate-200">Technical stack</div>
            <div className="mt-2 grid grid-cols-1 gap-1 md:grid-cols-2 text-slate-400">
              <div>Frontend: React + TypeScript + Vite</div>
              <div>Application layer: FastAPI services</div>
              <div>Execution: multi-provider GPU lot orchestration</div>
              <div>Verification: canonical hashing + equivalence + adversarial checks</div>
              <div>Settlement: receipt-root anchoring + on-chain verification</div>
              <div>Market: futures-style matching with reliability-aware execution</div>
            </div>
          </div>
          <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
            <div className="text-slate-200">Research insight</div>
            <div className="mt-1 space-y-1 text-slate-400">
              <div>Compute clearing quality depends on verified delivery, not raw machine time.</div>
              <div>
                Accepted-Delivery weighted pricing and explicit verification constraints reduce
                settlement risk and reward reliable providers.
              </div>
            </div>
          </div>
        </div>

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
            <div className="text-sm text-slate-100">Market agent engine</div>
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
          <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
            <label className="text-slate-400">
              Buyers
              <input
                type="number"
                min={10}
                max={5000}
                value={simBuyerAgents}
                onChange={(e) => setSimBuyerAgents(Math.max(10, Number(e.target.value) || 10))}
                className="mt-1 h-8 w-full rounded border border-slate-700 bg-slate-900 px-2 text-slate-100"
              />
            </label>
            <label className="text-slate-400">
              Sellers
              <input
                type="number"
                min={10}
                max={5000}
                value={simSellerAgents}
                onChange={(e) => setSimSellerAgents(Math.max(10, Number(e.target.value) || 10))}
                className="mt-1 h-8 w-full rounded border border-slate-700 bg-slate-900 px-2 text-slate-100"
              />
            </label>
            <label className="text-slate-400">
              Ticks/sec
              <input
                type="number"
                min={1}
                max={30}
                value={simTicksPerSecond}
                onChange={(e) => setSimTicksPerSecond(Math.max(1, Number(e.target.value) || 1))}
                className="mt-1 h-8 w-full rounded border border-slate-700 bg-slate-900 px-2 text-slate-100"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              className="bg-slate-800 border-slate-700"
              disabled={simBusy}
              onClick={() => {
                setSimBuyerAgents(120);
                setSimSellerAgents(90);
                setSimTicksPerSecond(3);
              }}
            >
              Conservative profile
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="bg-slate-800 border-slate-700"
              disabled={simBusy}
              onClick={() => {
                setSimBuyerAgents(360);
                setSimSellerAgents(300);
                setSimTicksPerSecond(5);
              }}
            >
              Presentation profile
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="bg-slate-800 border-slate-700"
              disabled={simBusy}
              onClick={() => {
                setSimBuyerAgents(700);
                setSimSellerAgents(550);
                setSimTicksPerSecond(8);
              }}
            >
              High-throughput profile
            </Button>
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
                    synthetic_buyer_agents: simBuyerAgents,
                    synthetic_seller_agents: simSellerAgents,
                    ticks_per_second: simTicksPerSecond,
                  });
                  setSimStatus(status);
                } finally {
                  setSimBusy(false);
                }
              }}
            >
              Start engine
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
              Stop engine
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
