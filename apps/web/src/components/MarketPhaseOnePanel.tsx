import { useEffect, useMemo, useRef, useState } from 'react';
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
  MarketApi,
  PlatformApi,
  VoucherApi,
  type ComputeDeliveryResponseDto,
  type DemoProviderExecutionResponseDto,
  type DemoRunResponseDto,
  type DemoRunTrackResponseDto,
  type GpuBackendStatusDto,
  type MarketPositionResponseDto,
  type ProductKeyDto,
  type VoucherBalanceResponseDto,
  type WindowDto,
} from '../lib/api';

type Region = WindowDto['region'];
type Sla = WindowDto['sla'];
type Tier = WindowDto['tier'];

type Props = {
  selectedGPU: string;
};

const gpuBasePrices: Record<string, number> = {
  'RTX 4090': 2.45,
  A100: 4.8,
  H100: 8.95,
  'RTX 3090': 1.2,
};

function formatProductKey(productKey: WindowDto) {
  return `${productKey.region} · ${productKey.iso_hour}h · ${productKey.sla} · ${productKey.tier}`;
}

function strVal(v: unknown): string | undefined {
  return typeof v === 'string' ? v : v != null ? String(v) : undefined;
}

function numVal(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

/** Renders remote `ecm_then_cado_multi_gpu` summary JSON (ECM + CADO-NFS pipeline). */
function FactoringSummaryReceipt({
  label,
  summary,
}: {
  label: string;
  summary: Record<string, unknown>;
}) {
  const method = strVal(summary.method);
  const inputN = strVal(summary.input_n);
  const factors = summary.final_prime_factors;
  const factorList = Array.isArray(factors)
    ? factors.map((x) => String(x))
    : factors != null
      ? [String(factors)]
      : [];
  const ecm = numVal(summary.ecm_elapsed_sec);
  const cado = numVal(summary.cado_elapsed_sec);
  const total = numVal(summary.total_elapsed_sec);
  const cadoRuns = summary.cado_runs;
  const cadoCount = Array.isArray(cadoRuns) ? cadoRuns.length : 0;
  const gpuDev = summary.gpu_devices;
  const gpuList = Array.isArray(gpuDev) ? gpuDev.map((g) => String(g)) : [];

  return (
    <div className="rounded-lg border border-slate-700/80 bg-slate-950/60 p-3 space-y-2">
      <div className="text-xs font-semibold text-cyan-200/90">{label}</div>
      <div className="grid gap-1 text-xs text-slate-300 sm:grid-cols-2">
        {method ? (
          <div>
            <span className="text-slate-500">Pipeline: </span>
            {method}
          </div>
        ) : null}
        {inputN ? (
          <div className="sm:col-span-2 font-mono break-all">
            <span className="text-slate-500">Composite (N): </span>
            {inputN}
          </div>
        ) : null}
        {gpuList.length ? (
          <div>
            <span className="text-slate-500">GPU devices: </span>
            {gpuList.join(', ')}
          </div>
        ) : null}
        {factorList.length ? (
          <div className="sm:col-span-2">
            <span className="text-slate-500">Prime factors: </span>
            <span className="font-mono text-emerald-200/90">{factorList.join(' × ')}</span>
          </div>
        ) : null}
        {ecm != null || cado != null || total != null ? (
          <div className="sm:col-span-2 text-slate-400">
            Timings — ECM: {ecm != null ? `${ecm.toFixed(3)}s` : '—'} · CADO:{' '}
            {cado != null ? `${cado.toFixed(3)}s` : '—'} · total:{' '}
            {total != null ? `${total.toFixed(3)}s` : '—'}
          </div>
        ) : null}
        <div className="sm:col-span-2 text-slate-500">
          CADO-NFS stages recorded: {cadoCount > 0 ? `${cadoCount} run(s)` : '0 (often ECM-only for small N)'}
        </div>
      </div>
      <details className="group">
        <summary className="cursor-pointer text-xs text-cyan-400/90 hover:text-cyan-300">
          Full CADO-NFS / ECM JSON (exact server payload)
        </summary>
        <pre className="mt-2 max-h-52 overflow-auto rounded border border-slate-800 bg-slate-950 p-2 text-[10px] leading-relaxed text-slate-400 whitespace-pre-wrap break-all">
          {JSON.stringify(summary, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function DemoExecutionReceiptCard({ run }: { run: DemoRunResponseDto }) {
  const anchor = run.blockchain_anchor;
  return (
    <Card className="bg-slate-900 border-slate-700 p-6 space-y-5">
      <div>
        <h3 className="text-slate-100 text-base font-semibold">Execution receipt · one-click demo</h3>
        <p className="mt-1 text-xs text-slate-500">
          Futures → vouchers → matched providers → remote ECM/CADO-NFS → verification → anchor.
        </p>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-xs space-y-1">
        <div className="font-medium text-slate-300">Receipt identifiers</div>
        <div className="font-mono text-slate-400 break-all">
          <span className="text-slate-500">Job: </span>
          {run.job_id}
        </div>
        <div className="font-mono text-slate-400 break-all">
          <span className="text-slate-500">Position: </span>
          {run.position_id}
        </div>
        <div>
          <span className="text-slate-500">Run status: </span>
          {run.run_status}
        </div>
        <div>
          <span className="text-slate-500">Settlement: </span>
          {run.settlement_status} · target {run.settlement_target_seconds}s · delivered{' '}
          {run.delivered_ngh.toFixed(2)} NGH · wallet remainder {run.remaining_wallet_ngh.toFixed(2)} NGH
        </div>
      </div>

      <div>
        <div className="text-sm font-medium text-slate-200 mb-2">Parties &amp; matching</div>
        <ul className="space-y-2 text-xs text-slate-300">
          <li>
            <span className="text-slate-500">Market policy: </span>
            {run.provider_selection_policy}
          </li>
          <li>
            <span className="text-slate-500">Real-provider-only: </span>
            {run.real_provider_only ? 'yes' : 'no'} ·{' '}
            <span className="text-slate-500">Synthetic excluded: </span>
            {run.synthetic_excluded ? 'yes' : 'no'}
          </li>
          <li>
            <span className="text-slate-500">Total GPUs allocated (market): </span>
            {run.matched_gpu_count}
          </li>
          {run.provider_executions.map((row: DemoProviderExecutionResponseDto, idx: number) => (
            <li
              key={`${row.provider_id}-${idx}`}
              className="rounded border border-slate-800/80 bg-slate-950/30 px-2 py-1.5"
            >
              <span className="text-slate-400">Provider {idx + 1}: </span>
              <span className="font-mono text-slate-200">{row.provider_id}</span>
              <span className="text-slate-500"> · </span>
              {row.gpu_count} GPU(s)
            </li>
          ))}
        </ul>
      </div>

      <div>
        <div className="text-sm font-medium text-slate-200 mb-2">CADO-NFS / GPU pipeline output</div>
        <div className="space-y-3">
          {run.provider_executions.map((row: DemoProviderExecutionResponseDto, idx: number) => (
            <FactoringSummaryReceipt
              key={`fs-${row.provider_id}-${idx}`}
              label={`${row.provider_id} · ${row.gpu_count} GPU`}
              summary={row.factoring_summary}
            />
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/15 p-3">
        <div className="text-sm font-medium text-emerald-200/90 mb-1">Verification</div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            className={
              run.verification_passed ? 'bg-emerald-700 text-white hover:bg-emerald-700' : 'bg-red-800 text-white'
            }
          >
            {run.verification_passed ? 'Hash check passed' : 'Hash check failed'}
          </Badge>
        </div>
        <div className="mt-2 text-[11px] font-mono text-slate-400 break-all">
          {run.verification_hash}
        </div>
      </div>

      <div className="rounded-lg border border-cyan-900/40 bg-cyan-950/20 p-3">
        <div className="text-sm font-medium text-cyan-200/90 mb-1">Blockchain anchor</div>
        <div className="text-xs text-slate-300 space-y-1">
          <div>
            <span className="text-slate-500">Network: </span>
            {anchor.network_label}
          </div>
          {anchor.block_number != null ? (
            <div>
              <span className="text-slate-500">Block: </span>
              {anchor.block_number}
            </div>
          ) : null}
          <div className="font-mono text-[11px] break-all text-cyan-100/90">
            <span className="text-slate-500">Tx hash: </span>
            {anchor.tx_hash}
          </div>
          {anchor.explorer_url ? (
            <a
              href={anchor.explorer_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block text-cyan-400 hover:text-cyan-300 underline text-xs"
            >
              Open in block explorer
            </a>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

function DeliveryExecutionReceiptCard({ d }: { d: ComputeDeliveryResponseDto }) {
  return (
    <Card className="bg-slate-900 border-slate-700 p-6 space-y-4">
      <div>
        <h3 className="text-slate-100 text-base font-semibold">Execution receipt · deliver &amp; compute</h3>
        <p className="mt-1 text-xs text-slate-500">Manual delivery path: vouchers → job → remote factor run.</p>
      </div>
      <div className="text-xs font-mono text-slate-400 break-all space-y-1">
        <div>
          <span className="text-slate-500">Position: </span>
          {d.position_id}
        </div>
        <div>
          <span className="text-slate-500">Job: </span>
          {d.job_id}
        </div>
        <div>
          {d.delivered_ngh.toFixed(2)} NGH delivered · wallet remainder {d.remaining_wallet_ngh.toFixed(2)} NGH ·{' '}
          {d.delivery_status}
        </div>
      </div>
      <FactoringSummaryReceipt label="GPU / CADO-NFS output" summary={d.factoring_summary} />
    </Card>
  );
}

/** Match `market_simulator` GPU templates so synthetic nominations cover this window. */
function productWindowForGpuModel(gpu: string): Pick<WindowDto, 'region' | 'sla' | 'tier'> {
  if (gpu === 'RTX 3090') return { region: 'us-west', sla: 'standard', tier: 'basic' };
  if (gpu === 'A100') return { region: 'asia-pacific', sla: 'premium', tier: 'premium' };
  if (gpu === 'H100') return { region: 'us-east', sla: 'urgent', tier: 'enterprise' };
  return { region: 'eu-central', sla: 'standard', tier: 'standard' };
}

export function MarketPhaseOnePanel({ selectedGPU }: Props) {
  const initialWin = productWindowForGpuModel(selectedGPU);
  const [region, setRegion] = useState<Region>(initialWin.region);
  const [isoHour, setIsoHour] = useState<number>(new Date().getUTCHours());
  const [sla, setSla] = useState<Sla>(initialWin.sla);
  const [tier, setTier] = useState<Tier>(initialWin.tier);
  const [quantityNgh, setQuantityNgh] = useState<number>(10);
  const [pricePerNgh, setPricePerNgh] = useState<number>(gpuBasePrices[selectedGPU] ?? 2.45);
  const [jobId, setJobId] = useState('');

  const [positions, setPositions] = useState<MarketPositionResponseDto[]>([]);
  const [vouchers, setVouchers] = useState<VoucherBalanceResponseDto[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deliveryComposite, setDeliveryComposite] = useState<string>('143');
  const [deliveryGpuCount, setDeliveryGpuCount] = useState<number>(4);
  const [lastDelivery, setLastDelivery] = useState<ComputeDeliveryResponseDto | null>(null);
  const [lastDemoRun, setLastDemoRun] = useState<DemoRunResponseDto | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [fullDemoBusy, setFullDemoBusy] = useState(false);
  const [fullDemoTrack, setFullDemoTrack] = useState<DemoRunTrackResponseDto | null>(null);
  const [fullDemoError, setFullDemoError] = useState<string | null>(null);
  const fullDemoPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [gpuBackend, setGpuBackend] = useState<GpuBackendStatusDto | null>(null);
  const [gpuBackendError, setGpuBackendError] = useState<string | null>(null);
  const [gpuBackendBusy, setGpuBackendBusy] = useState(false);

  useEffect(() => {
    setPricePerNgh(gpuBasePrices[selectedGPU] ?? 2.45);
    const w = productWindowForGpuModel(selectedGPU);
    setRegion(w.region);
    setSla(w.sla);
    setTier(w.tier);
    setIsoHour(new Date().getUTCHours());
  }, [selectedGPU]);

  const productKey = useMemo(
    () => ({
      region,
      iso_hour: isoHour,
      sla,
      tier,
    }),
    [region, isoHour, sla, tier],
  );

  function applyProductKeyForDeposit(pk: ProductKeyDto) {
    setRegion(pk.region);
    setIsoHour(pk.iso_hour);
    setSla(pk.sla);
    setTier(pk.tier);
    setStatus(`Manual path set to ${formatProductKey(pk)} — deposit will draw from that bucket’s wallet.`);
  }

  async function refresh() {
      const [nextPositions, nextVouchers] = await Promise.all([
      MarketApi.listPositions(80),
      VoucherApi.listVouchers(),
    ]);
    setPositions(nextPositions);
    setVouchers(nextVouchers);
  }

  useEffect(() => {
    void refresh().catch((err) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, []);

  async function loadGpuBackend() {
    setGpuBackendBusy(true);
    setGpuBackendError(null);
    try {
      const s = await PlatformApi.getGpuBackend();
      setGpuBackend(s);
    } catch (err) {
      setGpuBackend(null);
      setGpuBackendError(err instanceof Error ? err.message : String(err));
    } finally {
      setGpuBackendBusy(false);
    }
  }

  useEffect(() => {
    void loadGpuBackend();
  }, []);

  useEffect(() => {
    return () => {
      if (fullDemoPollRef.current) {
        clearInterval(fullDemoPollRef.current);
        fullDemoPollRef.current = null;
      }
    };
  }, []);

  async function run(action: () => Promise<void>) {
    setIsBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsBusy(false);
    }
  }

  function stepStatusClass(status: string) {
    if (status === 'done') return 'text-emerald-400';
    if (status === 'running') return 'text-amber-300';
    if (status === 'failed') return 'text-red-300';
    return 'text-slate-500';
  }

  async function startOneClickFullDemo() {
    if (fullDemoPollRef.current) {
      clearInterval(fullDemoPollRef.current);
      fullDemoPollRef.current = null;
    }
    setFullDemoError(null);
    setFullDemoBusy(true);
    setFullDemoTrack(null);
    try {
      const { run_id } = await MarketApi.startFullDemo({
        composite: deliveryComposite.trim(),
        region: productKey.region,
        iso_hour: productKey.iso_hour,
        sla: productKey.sla,
        tier: productKey.tier,
        quantity_ngh: quantityNgh,
        price_per_ngh: pricePerNgh,
        package_size_ngh: 10,
        gpu_model_label: selectedGPU,
        target_settle_seconds: 300,
      });

      const pollOnce = async () => {
        try {
          let track = await MarketApi.getDemoRunProgress(run_id, { slim: true });
          if (track.overall_status === 'completed' && !track.result) {
            track = await MarketApi.getDemoRunProgress(run_id);
          }
          setFullDemoTrack(track);
          if (track.overall_status === 'completed' && track.result) {
            setLastDemoRun(track.result);
            if (track.job_id) setJobId(track.job_id);
            setStatus(
              `One-click demo complete · job ${track.job_id} · tx ${track.result.blockchain_anchor.tx_hash.slice(0, 12)}…`,
            );
            await refresh();
            setFullDemoBusy(false);
            if (fullDemoPollRef.current) {
              clearInterval(fullDemoPollRef.current);
              fullDemoPollRef.current = null;
            }
            return;
          }
          if (track.overall_status === 'failed') {
            setFullDemoError(track.error ?? 'Demo run failed');
            setFullDemoBusy(false);
            if (fullDemoPollRef.current) {
              clearInterval(fullDemoPollRef.current);
              fullDemoPollRef.current = null;
            }
          }
        } catch (err) {
          setFullDemoError(err instanceof Error ? err.message : String(err));
          setFullDemoBusy(false);
          if (fullDemoPollRef.current) {
            clearInterval(fullDemoPollRef.current);
            fullDemoPollRef.current = null;
          }
        }
      };

      await pollOnce();
      fullDemoPollRef.current = setInterval(() => {
        void pollOnce();
      }, 650);
    } catch (err) {
      setFullDemoError(err instanceof Error ? err.message : String(err));
      setFullDemoBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <Card className="bg-slate-900 border-slate-800 p-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-slate-100">Physical Delivery Funding</h3>
            <p className="mt-2 text-sm text-slate-400">
              Acquire deliverable compute exposure, settle it into vouchers, and allocate vouchers
              to active jobs.
            </p>
          </div>
          <Badge variant="outline" className="border-blue-800 text-blue-300">
            Futures to Vouchers
          </Badge>
        </div>

        <div className="mt-5 rounded-lg border border-slate-700 bg-slate-950/50 p-4 space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                GPU factoring backend
              </div>
              <p className="mt-1 text-xs text-slate-400">
                One-click demo calls your CADO server (<code className="text-slate-300">remote_factor_server</code>
                ). This checks that CoreIndex can open a TCP connection to the URL you configured in{' '}
                <code className="text-slate-300">apps/api/.env</code>.
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="border-slate-600 bg-slate-800/80 shrink-0"
              disabled={gpuBackendBusy}
              onClick={() => void loadGpuBackend()}
            >
              {gpuBackendBusy ? 'Checking…' : 'Recheck'}
            </Button>
          </div>
          {gpuBackendError ? (
            <div className="text-xs text-red-300">{gpuBackendError}</div>
          ) : null}
          {gpuBackend ? (
            <div className="space-y-2 text-xs">
              {!gpuBackend.requests_installed ? (
                <div className="rounded border border-amber-800/60 bg-amber-950/30 px-2 py-1.5 text-amber-200">
                  Python package <code className="text-amber-100">requests</code> is missing in the API
                  environment. Run: <code className="text-amber-100">pip install requests</code>
                </div>
              ) : null}
              {gpuBackend.tcp_reachable ? (
                <div className="rounded border border-emerald-900/50 bg-emerald-950/20 px-2 py-1.5 text-emerald-200">
                  Reachable at <span className="font-mono">{gpuBackend.configured_base_url}</span> — ready to
                  run the factoring step.
                </div>
              ) : (
                <div className="rounded border border-amber-900/50 bg-amber-950/15 px-2 py-1.5 text-amber-100/95 space-y-1">
                  <div>
                    No TCP connection to <span className="font-mono">{gpuBackend.configured_base_url}</span>
                    {gpuBackend.tcp_error ? (
                      <span className="text-amber-200/80"> ({gpuBackend.tcp_error})</span>
                    ) : null}
                    . Start the GPU server or fix SSH port forwarding, then Recheck.
                  </div>
                  <p className="text-slate-400 leading-relaxed">{gpuBackend.setup_hint}</p>
                </div>
              )}
              <div className="font-mono text-[10px] text-slate-500 break-all">
                CoreIndex will POST → {gpuBackend.factor_post_url}
              </div>
            </div>
          ) : null}
        </div>

        <div className="mt-5 rounded-lg border border-cyan-800/50 bg-cyan-950/20 p-4 space-y-4">
          <div>
            <div className="text-sm text-cyan-200">One-click demo (easiest)</div>
            <p className="mt-1 text-xs text-cyan-100/80">
              Creates the job, opens a buy position, settles, matches providers against the live synthetic
              book (unless the API sets <code className="text-cyan-200/90">DEMO_REQUIRE_REAL_PROVIDERS</code>),
              runs the remote <strong>ECM-then-CADO-NFS</strong> pipeline on the allocated GPUs, then anchors
              verification. Tiny composites (e.g. 143 = 11×13) often complete in ECM only—
              <code className="text-cyan-200/90">cado_runs</code> may be empty; that is normal. The run uses the{' '}
              <strong>current UTC hour</strong> so the window lines up with the market simulator. Composite must be
              digits only (at least 2).
            </p>
            <Button
              className="mt-3 w-full bg-cyan-600 hover:bg-cyan-700 sm:w-auto"
              disabled={
                fullDemoBusy ||
                isBusy ||
                !/^\d{2,}$/.test(deliveryComposite.trim())
              }
              onClick={() => void startOneClickFullDemo()}
            >
              {fullDemoBusy ? 'Demo running…' : 'Run entire demo (one click)'}
            </Button>
            {fullDemoError ? (
              <div className="mt-2 text-xs text-red-300">{fullDemoError}</div>
            ) : null}
          </div>
          {fullDemoTrack?.steps?.length ? (
            <div className="rounded-md border border-cyan-900/40 bg-slate-950/40 p-3">
              <div className="text-xs font-medium text-cyan-200/90 mb-2">Live steps</div>
              <ul className="space-y-2 text-xs">
                {fullDemoTrack.steps.map((step) => (
                  <li key={step.step_id} className="flex flex-col gap-0.5 border-b border-slate-800/80 pb-2 last:border-0 last:pb-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-slate-200">{step.label}</span>
                      <span className={`uppercase tracking-wide ${stepStatusClass(step.status)}`}>
                        {step.status}
                      </span>
                    </div>
                    {step.detail ? (
                      <span className="text-slate-500 font-mono break-all">{step.detail}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="border-t border-cyan-900/30 pt-3">
            <div className="text-xs text-cyan-200/90">Manual path</div>
            <div className="mt-1 text-xs text-cyan-100/70">
              Or use Buy Exposure, then Run Full Demo Flow on a position when you already have a job ID.
            </div>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-4">
          <div className="space-y-2">
            <div className="text-xs text-slate-400">Region</div>
            <Select value={region} onValueChange={(v) => setRegion(v as Region)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue />
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
            <div className="text-xs text-slate-400">ISO hour</div>
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
            <Select value={sla} onValueChange={(v) => setSla(v as Sla)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue />
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
                <SelectValue />
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

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <div className="text-xs text-slate-400">Quantity (NGH)</div>
            <Input
              type="number"
              min={1}
              step={1}
              value={quantityNgh}
              onChange={(e) => setQuantityNgh(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
            />
          </div>

          <div className="space-y-2">
            <div className="text-xs text-slate-400">Price per NGH</div>
            <Input
              type="number"
              min={0.01}
              step={0.01}
              value={pricePerNgh}
              onChange={(e) => setPricePerNgh(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
            />
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-4">
          <div className="text-sm text-slate-300">Current product key</div>
          <div className="mt-1 text-sm text-slate-100">{formatProductKey(productKey)}</div>
          <div className="mt-2 text-sm text-slate-400">
            Selected market reference: {selectedGPU} at ${pricePerNgh.toFixed(2)} per NGH
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          <Button
            className="bg-blue-600 hover:bg-blue-700"
            disabled={isBusy}
            onClick={() =>
              void run(async () => {
                const position = await MarketApi.createPosition({
                  product_key: productKey,
                  side: 'buy',
                  quantity_ngh: quantityNgh,
                  price_per_ngh: pricePerNgh,
                });
                setStatus(`Created position ${position.position_id}`);
              })
            }
          >
            Buy Exposure
          </Button>

          <Button
            variant="outline"
            className="bg-slate-800 border-slate-700"
            disabled={isBusy}
            onClick={() => void refresh()}
          >
            Refresh
          </Button>
        </div>

        <div className="mt-6">
          <div className="text-sm text-slate-100">Open positions</div>
          <div className="mt-3 max-h-[min(22rem,45vh)] overflow-y-auto overscroll-contain space-y-3 pr-1">
            {positions.length ? (
              positions.map((position) => (
                <div
                  key={position.position_id}
                  className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"
                >
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="space-y-1">
                      <div className="text-sm text-slate-100">{formatProductKey(position.product_key)}</div>
                      <div className="text-xs text-slate-400">
                        {position.side} · {position.quantity_ngh} NGH · ${position.price_per_ngh.toFixed(2)} / NGH
                      </div>
                      <div className="text-xs text-slate-500">{position.position_id}</div>
                    </div>

                    <div className="flex items-center gap-3">
                      <Badge
                        variant="outline"
                        className={
                          position.status === 'settled'
                            ? 'border-emerald-800 text-emerald-300'
                            : 'border-amber-800 text-amber-300'
                        }
                      >
                        {position.status}
                      </Badge>
                      <Button
                        size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700"
                        disabled={isBusy || position.status === 'settled'}
                        onClick={() =>
                          void run(async () => {
                            const settled = await MarketApi.settlePosition(position.position_id);
                            setStatus(`Settled position ${settled.position_id} into vouchers`);
                          })
                        }
                      >
                        Settle to Vouchers
                      </Button>
                      <Button
                        size="sm"
                        className="bg-violet-600 hover:bg-violet-700"
                        disabled={isBusy || position.status !== 'settled' || !jobId.trim()}
                        onClick={() =>
                          void run(async () => {
                            const result = await MarketApi.deliverPosition(position.position_id, {
                              job_id: jobId.trim(),
                              gpu_count: deliveryGpuCount,
                              composite: deliveryComposite.trim(),
                            });
                            setLastDelivery(result);
                            setStatus(
                              `Delivered ${result.delivered_ngh.toFixed(2)} NGH and completed GPU factoring run`,
                            );
                          })
                        }
                      >
                        Deliver and Run Compute
                      </Button>
                      <Button
                        size="sm"
                        className="bg-cyan-600 hover:bg-cyan-700"
                        disabled={isBusy || !jobId.trim()}
                        onClick={() =>
                          void run(async () => {
                            const result = await MarketApi.runDemo(position.position_id, {
                              job_id: jobId.trim(),
                              composite: deliveryComposite.trim(),
                              target_settle_seconds: 300,
                              auto_settle_if_open: true,
                            });
                            setLastDemoRun(result);
                            setStatus(
                              `Demo run complete · tx ${result.blockchain_anchor.tx_hash.slice(0, 12)}... · verification ${result.verification_passed ? 'passed' : 'failed'}`,
                            );
                          })
                        }
                      >
                        Run Full Demo Flow
                      </Button>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
                No positions yet. Buy exposure to start the futures-to-vouchers flow.
              </div>
            )}
          </div>
        </div>
      </Card>

      <div className="space-y-6">
        <Card className="bg-slate-900 border-slate-800 p-6">
          <div className="text-slate-100">Voucher balances</div>
          <div className="mt-3 space-y-3">
            {vouchers.length ? (
              vouchers.map((voucher, index) => (
                <div
                  key={`${formatProductKey(voucher.product_key)}-${index}`}
                  className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"
                >
                  <div className="text-sm text-slate-100">{formatProductKey(voucher.product_key)}</div>
                  <div className="mt-2 text-sm text-slate-400">
                    Wallet: {voucher.balance_ngh.toFixed(2)} NGH
                  </div>
                  <div className="text-sm text-slate-500">
                    Deposited: {voucher.deposited_ngh.toFixed(2)} NGH
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3 border-slate-600 text-slate-200"
                    disabled={isBusy}
                    onClick={() => applyProductKeyForDeposit(voucher.product_key)}
                  >
                    Use this bucket for deposit
                  </Button>
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
                No vouchers yet. Settle a market position first.
              </div>
            )}
          </div>
        </Card>

        <Card className="bg-slate-900 border-slate-800 p-6">
          <div className="text-slate-100">Deposit vouchers to a job</div>
          <div className="mt-2 space-y-2 text-sm text-slate-400">
            <p>
              Deposits only spend the <span className="text-slate-200">wallet</span> balance for the
              exact product key shown under &quot;Current product key&quot; (region · hour · SLA ·
              tier). Your us-east vouchers cannot fund an eu-central job until you align those
              fields—or click <span className="text-slate-200">Use this bucket for deposit</span> on
              the voucher row you want.
            </p>
            <p>
              The one-click demo already escrows vouchers for its job; you usually do not need to
              deposit again for that same run.
            </p>
          </div>

          <div className="mt-4 space-y-3">
            <Input
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="job-123"
              className="bg-slate-800 border-slate-700"
            />
            <Button
              className="w-full bg-violet-600 hover:bg-violet-700"
              disabled={isBusy || !jobId.trim()}
              onClick={() =>
                void run(async () => {
                  const deposit = await VoucherApi.deposit({
                    job_id: jobId.trim(),
                    product_key: productKey,
                    amount_ngh: quantityNgh,
                  });
                  setStatus(
                    `Deposited ${deposit.deposited_ngh.toFixed(2)} NGH to job ${deposit.job_id}`,
                  );
                })
              }
            >
              Deposit ({formatProductKey(productKey)})
            </Button>
            <Input
              type="number"
              min={1}
              max={4}
              step={1}
              value={deliveryGpuCount}
              onChange={(e) => setDeliveryGpuCount(Number(e.target.value))}
              className="bg-slate-800 border-slate-700"
              placeholder="GPU count (1-4)"
            />
            <Input
              value={deliveryComposite}
              onChange={(e) => setDeliveryComposite(e.target.value)}
              className="bg-slate-800 border-slate-700"
              placeholder="e.g. 143 (11×13) for a quick GPU check"
            />
            <div className="text-xs text-slate-500">
              Provider pairing and GPU count are now matched automatically by the market at execution.
            </div>
          </div>
        </Card>

        {(status || error) && (
          <Card className="bg-slate-900 border-slate-800 p-6">
            <div className="text-slate-100">Funding activity</div>
            {status ? <div className="mt-3 text-sm text-emerald-300">{status}</div> : null}
            {error ? <div className="mt-3 text-sm text-red-200">{error}</div> : null}
          </Card>
        )}
        {lastDemoRun ? <DemoExecutionReceiptCard run={lastDemoRun} /> : null}
        {lastDelivery ? <DeliveryExecutionReceiptCard d={lastDelivery} /> : null}
      </div>
    </div>
  );
}
