import { useEffect, useMemo, useState } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  ProviderApi,
  type ProviderExecutionMetricsResponseDto,
  type ProviderFleetOverviewResponseDto,
  type ProviderSlaSummaryResponseDto,
  type WindowDto,
} from '../lib/api';
import { MyLots } from './MyLots';

type Region = WindowDto['region'];
type SLA = WindowDto['sla'];
type Tier = WindowDto['tier'];

function pretty(obj: unknown) {
  return JSON.stringify(obj, null, 2);
}

function utcHourNow(): number {
  return new Date().getUTCHours();
}

export function ProviderSim() {
  const [region, setRegion] = useState<Region>('us-east');
  const [isoHour, setIsoHour] = useState<number>(utcHourNow());
  const [sla, setSla] = useState<SLA>('standard');
  const [tier, setTier] = useState<Tier>('standard');

  const [nghAvailable, setNghAvailable] = useState<number>(30);
  const [gpuModel, setGpuModel] = useState<string>('RTX 4090');
  const [gpuCount, setGpuCount] = useState<number>(2);
  const [jobId, setJobId] = useState<string>('');
  const [lotId, setLotId] = useState<string>('');

  const [isBusy, setIsBusy] = useState(false);
  const [lastResponse, setLastResponse] = useState<unknown>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lotsRefreshTrigger, setLotsRefreshTrigger] = useState(0);
  const [slaSummary, setSlaSummary] = useState<ProviderSlaSummaryResponseDto | null>(null);
  const [executionMetrics, setExecutionMetrics] = useState<ProviderExecutionMetricsResponseDto | null>(
    null,
  );
  const [fleetOverview, setFleetOverview] = useState<ProviderFleetOverviewResponseDto | null>(null);

  const windowDto: WindowDto = useMemo(
    () => ({
      region,
      iso_hour: isoHour,
      sla,
      tier,
    }),
    [region, isoHour, sla, tier],
  );

  async function run<T>(fn: () => Promise<T>) {
    setIsBusy(true);
    setLastError(null);
    try {
      const res = await fn();
      setLastResponse(res);
      const [nextSla, nextExec, nextFleet] = await Promise.all([
        ProviderApi.getSlaSummary(),
        ProviderApi.getExecutionMetrics(),
        ProviderApi.getFleetOverview(),
      ]);
      setSlaSummary(nextSla);
      setExecutionMetrics(nextExec);
      setFleetOverview(nextFleet);
      return res;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setLastError(msg);
      setLastResponse(null);
      throw e;
    } finally {
      setIsBusy(false);
    }
  }

  useEffect(() => {
    void Promise.all([
      ProviderApi.getSlaSummary(),
      ProviderApi.getExecutionMetrics(),
      ProviderApi.getFleetOverview(),
    ])
      .then(([slaRes, execRes, fleetRes]) => {
        setSlaSummary(slaRes);
        setExecutionMetrics(execRes);
        setFleetOverview(fleetRes);
      })
      .catch((e) => setLastError(e instanceof Error ? e.message : String(e)));
  }, [lotsRefreshTrigger]);

  return (
    <div className="space-y-6">
      <MyLots refreshTrigger={lotsRefreshTrigger} />

      <Card className="bg-slate-900 border-slate-800 p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-slate-100">Provider SLA Dashboard</h3>
          <Button
            variant="outline"
            className="bg-slate-800 border-slate-700"
            onClick={() =>
              void Promise.all([
                ProviderApi.getSlaSummary(),
                ProviderApi.getExecutionMetrics(),
                ProviderApi.getFleetOverview(),
              ])
                .then(([slaRes, execRes, fleetRes]) => {
                  setSlaSummary(slaRes);
                  setExecutionMetrics(execRes);
                  setFleetOverview(fleetRes);
                })
                .catch((e) => setLastError(e instanceof Error ? e.message : String(e)))
            }
          >
            Refresh SLA
          </Button>
        </div>
        {slaSummary ? (
          <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-4 text-sm">
            <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
              <div className="text-slate-500 text-xs uppercase">Lots</div>
              <div className="text-slate-100 mt-1">{slaSummary.total_lots}</div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
              <div className="text-slate-500 text-xs uppercase">Success Rate</div>
              <div className="text-emerald-300 mt-1">
                {(slaSummary.success_rate * 100).toFixed(1)}%
              </div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
              <div className="text-slate-500 text-xs uppercase">Avg Prepare</div>
              <div className="text-slate-100 mt-1">{slaSummary.avg_prepare_seconds.toFixed(1)}s</div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-950/40 p-3">
              <div className="text-slate-500 text-xs uppercase">Avg Completion</div>
              <div className="text-slate-100 mt-1">
                {slaSummary.avg_completion_seconds.toFixed(1)}s
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-4 text-sm text-slate-400">SLA metrics will appear after first lot activity.</div>
        )}
        {executionMetrics ? (
          <div className="mt-4 rounded border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
            <div>On-time prepare: {(executionMetrics.on_time_prepare_ratio * 100).toFixed(1)}%</div>
            <div>On-time completion: {(executionMetrics.on_time_completion_ratio * 100).toFixed(1)}%</div>
            <div>Average wall time: {executionMetrics.avg_wall_time_seconds.toFixed(1)}s</div>
          </div>
        ) : null}
        {fleetOverview ? (
          <div className="mt-4 rounded border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
            <div>Nominated capacity: {fleetOverview.nominated_ngh_total.toFixed(2)} NGH</div>
            <div>Active lots: {fleetOverview.lots_active}</div>
            <div>Completed lots: {fleetOverview.lots_completed}</div>
            <div>Utilization: {(fleetOverview.utilization_ratio * 100).toFixed(1)}%</div>
          </div>
        ) : null}
      </Card>

      <Card className="bg-slate-900 border-slate-800 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-slate-100">Provider Operations Desk</h2>
            <p className="text-slate-400 text-sm">
              Operate nominations and lot lifecycle from the provider side. This hits{' '}
              <Badge variant="outline" className="border-slate-700 text-slate-200">
                /nominations
              </Badge>{' '}
              and{' '}
              <Badge variant="outline" className="border-slate-700 text-slate-200">
                /lots
              </Badge>{' '}
              endpoints directly and mirrors the execution workflow.
            </p>
          </div>
          <Button
            variant="outline"
            className="bg-slate-800 border-slate-700"
            onClick={() => {
              setLastError(null);
              setLastResponse(null);
            }}
            disabled={isBusy}
          >
            Clear output
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mt-6">
          <div className="space-y-2">
            <div className="text-xs text-slate-400">Region</div>
            <Select value={region} onValueChange={(v) => setRegion(v as Region)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue placeholder="Select region" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="us-east">us-east</SelectItem>
                <SelectItem value="us-west">us-west</SelectItem>
                <SelectItem value="eu-central">eu-central</SelectItem>
                <SelectItem value="asia-pacific">asia-pacific</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="text-xs text-slate-400">ISO hour (UTC)</div>
            <Input
              type="number"
              min={0}
              max={23}
              value={isoHour}
              onChange={(e) => setIsoHour(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
            />
          </div>

          <div className="space-y-2">
            <div className="text-xs text-slate-400">SLA</div>
            <Select value={sla} onValueChange={(v) => setSla(v as SLA)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue placeholder="Select SLA" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">standard</SelectItem>
                <SelectItem value="premium">premium</SelectItem>
                <SelectItem value="urgent">urgent</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="text-xs text-slate-400">Tier</div>
            <Select value={tier} onValueChange={(v) => setTier(v as Tier)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue placeholder="Select tier" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="basic">basic</SelectItem>
                <SelectItem value="standard">standard</SelectItem>
                <SelectItem value="premium">premium</SelectItem>
                <SelectItem value="enterprise">enterprise</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
          <Card className="bg-slate-950/40 border-slate-800 p-4">
            <div className="text-slate-200 mb-3">1) Nominate capacity</div>
            <div className="text-xs text-slate-400 mb-2">GPU model</div>
            <Input
              value={gpuModel}
              onChange={(e) => setGpuModel(e.target.value)}
              className="bg-slate-800 border-slate-700"
              placeholder="RTX 4090"
            />
            <div className="text-xs text-slate-400 mt-2 mb-2">GPU count</div>
            <Input
              type="number"
              min={1}
              max={64}
              step={1}
              value={gpuCount}
              onChange={(e) => setGpuCount(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
            />
            <div className="text-xs text-slate-400 mb-2">NGH available</div>
            <Input
              type="number"
              min={0}
              step={1}
              value={nghAvailable}
              onChange={(e) => setNghAvailable(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
            />
            <Button
              className="w-full mt-3 bg-blue-600 hover:bg-blue-700"
              disabled={isBusy}
              onClick={() =>
                void run(() =>
                  ProviderApi.createNomination({
                    ...windowDto,
                    ngh_available: nghAvailable,
                    gpu_model: gpuModel.trim() || 'RTX 4090',
                    gpu_count: gpuCount,
                  }),
                )
              }
            >
              POST /nominations
            </Button>
          </Card>

          <Card className="bg-slate-950/40 border-slate-800 p-4">
            <div className="text-slate-200 mb-3">2) Create a lot</div>
            <div className="text-xs text-slate-400 mb-2">Job ID (optional)</div>
            <Input
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="job-123 (optional)"
              className="bg-slate-800 border-slate-700"
            />
            <Button
              className="w-full mt-3 bg-blue-600 hover:bg-blue-700"
              disabled={isBusy}
              onClick={() =>
                void run(async () => {
                  const lot = await ProviderApi.createLot({
                    window: windowDto,
                    job_id: jobId.trim() ? jobId.trim() : null,
                  });
                  setLotId(lot.lot_id);
                  setLotsRefreshTrigger((k) => k + 1);
                  return lot;
                })
              }
            >
              POST /lots
            </Button>
            <div className="text-xs text-slate-400 mt-3">
              Current lot_id:{' '}
              <span className="text-slate-200">{lotId || '(none yet)'}</span>
            </div>
          </Card>

          <Card className="bg-slate-950/40 border-slate-800 p-4">
            <div className="text-slate-200 mb-3">3) Advance lot status</div>
            <Button
              className="w-full bg-slate-800 hover:bg-slate-700 border border-slate-700"
              variant="outline"
              disabled={isBusy || !lotId}
              onClick={() =>
                void run(() =>
                  ProviderApi.prepareReady(lotId, {
                    device_ok: true,
                    driver_ok: true,
                    image_pulled: true,
                    inputs_prefetched: true,
                  }),
                )
              }
            >
              POST /lots/{'{lot_id}'}/prepare_ready
            </Button>

            <Button
              className="w-full mt-3 bg-green-600 hover:bg-green-700"
              disabled={isBusy || !lotId}
              onClick={() =>
                void run(() =>
                  ProviderApi.submitResult(lotId, {
                    output_root: `out-${Date.now().toString(16)}`,
                    item_count: 1000,
                    wall_time_seconds: 120,
                    raw_gpu_time_seconds: 110,
                    logs_uri: 'https://example.com/logs/demo',
                  }),
                )
              }
            >
              POST /lots/{'{lot_id}'}/result
            </Button>

            {!lotId && (
              <div className="text-xs text-amber-300 mt-3">
                Create a lot first to enable these buttons.
              </div>
            )}
          </Card>
        </div>
      </Card>

      <Card className="bg-slate-900 border-slate-800 p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-slate-100">Last API output</h3>
          {isBusy ? (
            <span className="text-xs text-slate-400">Working…</span>
          ) : null}
        </div>

        {lastError ? (
          <pre className="mt-4 text-xs text-red-200 whitespace-pre-wrap bg-red-950/30 border border-red-900/50 rounded-md p-3">
            {lastError}
          </pre>
        ) : null}

        {lastResponse ? (
          <pre className="mt-4 text-xs text-slate-200 whitespace-pre-wrap bg-slate-950/40 border border-slate-800 rounded-md p-3 overflow-auto max-h-[420px]">
            {pretty(lastResponse)}
          </pre>
        ) : (
          <div className="mt-4 text-sm text-slate-400">
            Use the buttons above to call the backend. Responses will show here.
          </div>
        )}
      </Card>
    </div>
  );
}

