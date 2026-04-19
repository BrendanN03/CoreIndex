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
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import {
  JobApi,
  MarketApi,
  PlatformApi,
  QcApi,
  SessionApi,
  SettlementApi,
  VoucherApi,
  type CollectiveSessionResponseDto,
  type ExecutionPreflightResponseDto,
  type DemoProviderExecutionResponseDto,
  type DemoRunResponseDto,
  type GpuBackendStatusDto,
  type JobReceiptsResponseDto,
  type MarketPositionResponseDto,
  type QcAdversarialMatrixResponseDto,
  type QcAdversarialSuiteResponseDto,
  type QcGoldCorpusCaseDto,
  type QcGoldCorpusEvaluateResponseDto,
  type QcGoldCorpusSavedReportDto,
  type QcGoldPassCriteriaDto,
  type QcCanonicalizeResponseDto,
  type QcCompareResponseDto,
  type QcHashResponseDto,
  type QcModeDto,
  type SettlementOnchainVerifyResponseDto,
  type SettlementRunResponseDto,
  type VoucherBalanceResponseDto,
  type WindowDto,
  type ProductKeyDto,
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

function validComposite(raw: string): boolean {
  return /^\d{2,}$/.test(raw.trim());
}

/** Must match API `target_settle_seconds` max (366 days). */
const MAX_TARGET_SETTLE_SECONDS = 366 * 24 * 3600;

type HorizonUnit = 'seconds' | 'minutes' | 'days' | 'months';

function horizonToSeconds(amount: number, unit: HorizonUnit): number {
  const a = Number.isFinite(amount) && amount > 0 ? amount : 1;
  let sec: number;
  switch (unit) {
    case 'seconds':
      sec = Math.floor(a);
      break;
    case 'minutes':
      sec = Math.floor(a * 60);
      break;
    case 'days':
      sec = Math.floor(a * 86400);
      break;
    case 'months':
      sec = Math.floor(a * 30 * 86400);
      break;
    default:
      sec = 300;
  }
  return Math.min(MAX_TARGET_SETTLE_SECONDS, Math.max(30, sec));
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
  const sanitizedSummary = { ...summary };
  // Hide backend-specific operational notes from receipt surfaces.
  delete sanitizedSummary.note;

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
          {JSON.stringify(sanitizedSummary, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function formatHorizonLabel(totalSeconds: number): string {
  const sec = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m (${sec}s)`;
  if (m > 0) return `${m}m ${s}s (${sec}s)`;
  return `${sec}s`;
}

/** Align with API `COREINDEX_LEGACY_MISSING_CLOSES_AT_SECONDS` default (300s). */
const LEGACY_CLOSE_FALLBACK_MS = 300_000;

function parseIsoToMs(iso?: string | null): number | null {
  if (!iso) return null;
  let trimmed = iso.trim();
  if (!trimmed.endsWith('Z') && !/[+-]\d{2}:?\d{2}$/.test(trimmed)) {
    trimmed = `${trimmed}Z`;
  }
  // Some engines choke on >3 fractional second digits; normalize to milliseconds.
  trimmed = trimmed.replace(/(\.\d{3})\d+(?=Z|[+-])/g, '$1');
  const ms = Date.parse(trimmed);
  return Number.isFinite(ms) ? ms : null;
}

function productKeysEqual(a: ProductKeyDto, b: ProductKeyDto): boolean {
  return a.region === b.region && a.iso_hour === b.iso_hour && a.sla === b.sla && a.tier === b.tier;
}

/** Milliseconds until this contract may settle / escrow; 0 means closed. Mirrors API `seconds_until_contract_close`. */
function positionMsUntilClose(p: MarketPositionResponseDto, nowMs: number): number {
  const explicitClose = parseIsoToMs(p.closes_at);
  if (explicitClose != null) return Math.max(0, explicitClose - nowMs);
  const horizonSec =
    typeof p.close_in_seconds === 'number' &&
    Number.isFinite(p.close_in_seconds) &&
    p.close_in_seconds >= 0
      ? Math.floor(p.close_in_seconds)
      : LEGACY_CLOSE_FALLBACK_MS / 1000;
  const created = parseIsoToMs(p.created_at);
  // Unparseable created_at: fail closed (same order of magnitude as API `10**9` seconds).
  if (created == null) return 1_000_000_000_000;
  return Math.max(0, created + horizonSec * 1000 - nowMs);
}

/** Prefer API `seconds_until_close`; fallback to client-side clock math. */
function positionSecondsUntilClose(p: MarketPositionResponseDto, nowMs: number): number {
  const raw = p.seconds_until_close;
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return Math.max(0, Math.floor(raw));
  }
  return Math.max(0, Math.ceil(positionMsUntilClose(p, nowMs) / 1000));
}

function positionContractClosed(p: MarketPositionResponseDto, nowMs: number): boolean {
  return positionSecondsUntilClose(p, nowMs) <= 0;
}

function parseJsonlRows(input: string): Record<string, unknown>[] {
  return input
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

type P2Preset = {
  name: string;
  schemaId: string;
  mode: QcModeDto;
  relTol: number;
  maxUlp: number;
  a: string;
  b: string;
};

const P2_PRESETS: Record<string, P2Preset> = {
  serializerVariance: {
    name: 'Serializer variance',
    schemaId: 'table@1',
    mode: 'bit_exact',
    relTol: 1e-4,
    maxUlp: 2,
    a: '{"id":"a","x":1.0,"meta":{"ok":true}}\n{"id":"b","x":2.0,"meta":{"ok":false}}\n',
    b: '{"x":2.0,"meta":{"ok":false},"id":"b"}\n{"meta":{"ok":true},"id":"a","x":1.0}\n',
  },
  fpJitter: {
    name: 'FP jitter',
    schemaId: 'vectors@1',
    mode: 'fp_tolerant',
    relTol: 1e-4,
    maxUlp: 2,
    a: '{"id":"v1","vector":[1.0,2.0,3.0]}\n',
    b: '{"id":"v1","vector":[1.0000000000000002,2.0,3.0]}\n',
  },
  fpDriftFail: {
    name: 'FP drift fail',
    schemaId: 'vectors@1',
    mode: 'fp_tolerant',
    relTol: 1e-4,
    maxUlp: 2,
    a: '{"id":"v1","vector":[1.2,2.0,3.0]}\n',
    b: '{"id":"v1","vector":[1.6,2.0,3.0]}\n',
  },
};

type P2CorpusCase = {
  id: string;
  title: string;
  description: string;
  schemaId: string;
  mode: QcModeDto;
  inputA: string;
  inputB: string;
  inputFormatA?: string;
  inputFormatB?: string;
  relTol?: number;
  maxUlp?: number;
  strategy: 'compare' | 'canonical_root';
  expectEqual: boolean;
};

type P2CorpusResult = {
  id: string;
  title: string;
  expectedEqual: boolean;
  observedEqual: boolean;
  passed: boolean;
  detail: string;
};

const P2_CORPUS: P2CorpusCase[] = [
  {
    id: 'serializer-key-order',
    title: 'Serializer key-order variance',
    description: 'Semantically same row, different JSON field order.',
    schemaId: 'table@1',
    mode: 'bit_exact',
    strategy: 'compare',
    expectEqual: true,
    inputA: '{"id":"a","ts_utc":"2026-01-01T00:00:00Z","x":1.2,"y":2.3}\n',
    inputB: '{"y":2.3,"x":1.2,"ts_utc":"2026-01-01T00:00:00Z","id":"a"}\n',
  },
  {
    id: 'float-jitter-pass',
    title: 'FP jitter within tolerance',
    description: 'Small numeric drift should pass fp_tolerant.',
    schemaId: 'vectors@1',
    mode: 'fp_tolerant',
    relTol: 1e-4,
    maxUlp: 2,
    strategy: 'compare',
    expectEqual: true,
    inputA: '{"id":"v1","vector":[1.0,2.0,3.0]}\n',
    inputB: '{"id":"v1","vector":[1.0000000000000002,2.0,3.0]}\n',
  },
  {
    id: 'float-jitter-fail',
    title: 'FP jitter beyond tolerance',
    description: 'Large numeric drift should fail fp_tolerant.',
    schemaId: 'vectors@1',
    mode: 'fp_tolerant',
    relTol: 1e-4,
    maxUlp: 2,
    strategy: 'compare',
    expectEqual: false,
    inputA: '{"id":"v1","vector":[1.2,2.0,3.0]}\n',
    inputB: '{"id":"v1","vector":[1.5,2.0,3.0]}\n',
  },
  {
    id: 'row-order-root',
    title: 'Row-order canonical root stability',
    description: 'Canonicalization should normalize row ordering by schema key.',
    schemaId: 'table@1',
    mode: 'bit_exact',
    strategy: 'canonical_root',
    expectEqual: true,
    inputFormatA: 'jsonl',
    inputFormatB: 'jsonl',
    inputA:
      '{"id":"b","ts":"2026-01-01T00:00:01Z","x":2.0,"y":3.0}\n{"id":"a","ts":"2026-01-01T00:00:00Z","x":1.0,"y":2.0}\n',
    inputB:
      '{"id":"a","ts_utc":"2026-01-01T00:00:00Z","x":1.0,"y":2.0}\n{"id":"b","ts_utc":"2026-01-01T00:00:01Z","x":2.0,"y":3.0}\n',
  },
  {
    id: 'csv-vs-jsonl',
    title: 'CSV vs JSONL canonical equivalence',
    description: 'Different source encodings should canonicalize to same root.',
    schemaId: 'table@1',
    mode: 'bit_exact',
    strategy: 'canonical_root',
    expectEqual: true,
    inputFormatA: 'csv',
    inputFormatB: 'jsonl',
    inputA: 'id,ts_utc,x,y\nalpha,2026-01-01T00:00:00Z,1.0,2.0\n',
    inputB: '{"id":"alpha","ts_utc":"2026-01-01T00:00:00Z","x":1.0,"y":2.0}\n',
  },
  {
    id: 'cado-mismatch',
    title: 'CADO relation mismatch',
    description: 'Material integer difference should fail equality.',
    schemaId: 'cado_relations@1',
    mode: 'bit_exact',
    strategy: 'compare',
    expectEqual: false,
    inputA: '{"a":1001,"b":2,"p":11,"q":13}\n',
    inputB: '{"a":1002,"b":2,"p":11,"q":13}\n',
  },
];

function ExecutionReceiptCard({ run }: { run: DemoRunResponseDto }) {
  const anchor = run.blockchain_anchor;
  const pk = run.futures_product_key;
  const factors = run.consolidated_prime_factors ?? [];
  const sellerCount = run.matched_seller_count ?? run.provider_executions.length;
  return (
    <Card className="bg-slate-900 border-slate-700 p-6 space-y-5">
      <div>
        <h3 className="text-slate-100 text-base font-semibold">Execution receipt · futures delivery</h3>
        <p className="mt-1 text-xs text-slate-500">
          Priced contract → vouchers → matched sellers (max 4) → per-seller GPU CADO-NFS → hash verification →
          blockchain anchor.
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
          <span className="text-slate-500">Buyer (owner): </span>
          <span className="font-mono">{run.buyer_owner_id ?? '—'}</span>
        </div>
        <div>
          <span className="text-slate-500">Run status: </span>
          {run.run_status}
        </div>
        <div>
          <span className="text-slate-500">Settlement: </span>
          {run.settlement_status} · horizon {formatHorizonLabel(run.settlement_target_seconds)} · delivered{' '}
          {run.delivered_ngh.toFixed(2)} NGH · wallet remainder {run.remaining_wallet_ngh.toFixed(2)} NGH
        </div>
        {pk ? (
          <div>
            <span className="text-slate-500">Contract window: </span>
            {formatProductKey(pk)}
          </div>
        ) : null}
        {run.futures_quantity_ngh != null && run.futures_price_per_ngh != null ? (
          <div>
            <span className="text-slate-500">Futures leg: </span>
            {run.futures_quantity_ngh.toFixed(2)} NGH @ ${run.futures_price_per_ngh.toFixed(4)}/NGH · notional $
            {(run.futures_contract_notional ?? run.futures_quantity_ngh * run.futures_price_per_ngh).toFixed(4)}
          </div>
        ) : null}
        {run.execution_market_price_per_ngh != null ? (
          <div>
            <span className="text-slate-500">Execution clearing price: </span>
            ${run.execution_market_price_per_ngh.toFixed(4)}/NGH · execution notional $
            {(run.execution_market_notional ?? run.execution_market_price_per_ngh * run.delivered_ngh).toFixed(4)}
          </div>
        ) : null}
        <div>
          <span className="text-slate-500">Integer factored (N): </span>
          <span className="font-mono text-cyan-200/90">{run.composite_to_factor ?? '—'}</span>
        </div>
        {factors.length ? (
          <div>
            <span className="text-slate-500">Reported prime factors: </span>
            <span className="font-mono text-emerald-200/90">{factors.join(' × ')}</span>
          </div>
        ) : null}
      </div>

      <div>
        <div className="text-sm font-medium text-slate-200 mb-2">Parties and matching</div>
        <ul className="space-y-2 text-xs text-slate-300">
          <li>
            <span className="text-slate-500">Distinct sellers matched: </span>
            {sellerCount} (max 4) ·{' '}
            <span className="text-slate-500">Total GPU slots: </span>
            {run.matched_gpu_count} (max 4, one slot per matched GPU on the book)
          </li>
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
          {run.provider_executions.map((row: DemoProviderExecutionResponseDto, idx: number) => (
            <li
              key={`${row.provider_id}-${idx}`}
              className="rounded border border-slate-800/80 bg-slate-950/30 px-2 py-1.5"
            >
              <span className="text-slate-400">Seller {idx + 1}: </span>
              <span className="font-mono text-slate-200">{row.provider_id}</span>
              <span className="text-slate-500"> · </span>
              {row.gpu_count} GPU(s) for CADO-NFS slice
              {row.indicative_price_per_ngh != null ? (
                <>
                  <span className="text-slate-500"> · </span>
                  list ~${row.indicative_price_per_ngh.toFixed(2)}/NGH
                </>
              ) : null}
              {row.provider_reliability_score != null ? (
                <>
                  <span className="text-slate-500"> · </span>
                  reliability {(row.provider_reliability_score * 100).toFixed(1)}%
                </>
              ) : null}
              {row.receipt_signature ? (
                <div className="mt-1 font-mono text-[10px] text-slate-500 break-all">
                  sig {row.receipt_signature.slice(0, 24)}...
                </div>
              ) : null}
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

function firstProviderFactoringSummary(run: DemoRunResponseDto | null): Record<string, unknown> | null {
  if (!run) return null;
  const first = run.provider_executions?.[0];
  if (!first || typeof first.factoring_summary !== 'object' || first.factoring_summary == null) return null;
  return first.factoring_summary;
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
  /** Per settled position: optional override for which integer N to send to /factor. */
  const [compositeByPosition, setCompositeByPosition] = useState<Record<string, string>>({});
  /** Futures settlement / receipt horizon (sent as `target_settle_seconds`). */
  const [contractHorizonAmount, setContractHorizonAmount] = useState<number>(1);
  const [contractHorizonUnit, setContractHorizonUnit] = useState<HorizonUnit>('minutes');
  const [positionClockNowMs, setPositionClockNowMs] = useState<number>(() => Date.now());
  const [preflightByPosition, setPreflightByPosition] = useState<
    Record<string, ExecutionPreflightResponseDto>
  >({});
  const [lastDemoRun, setLastDemoRun] = useState<DemoRunResponseDto | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [gpuBackend, setGpuBackend] = useState<GpuBackendStatusDto | null>(null);
  const [gpuBackendError, setGpuBackendError] = useState<string | null>(null);
  const [gpuBackendBusy, setGpuBackendBusy] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [sessionMembershipCsv, setSessionMembershipCsv] = useState('member-a,member-b');
  const [sessionWorldSize, setSessionWorldSize] = useState<number>(2);
  const [sessionReadyMember, setSessionReadyMember] = useState('member-a');
  const [activeSession, setActiveSession] = useState<CollectiveSessionResponseDto | null>(null);
  const [jobReceipts, setJobReceipts] = useState<JobReceiptsResponseDto | null>(null);
  const [qcPackageId, setQcPackageId] = useState('pkg-p1-1');
  const [qcProviderId, setQcProviderId] = useState('provider-1');
  const [receiptRoot, setReceiptRoot] = useState('0xabc12345');
  const [qcRoot, setQcRoot] = useState('0xdef67890');
  const [settlementRun, setSettlementRun] = useState<SettlementRunResponseDto | null>(null);
  const [settlementOnchainVerify, setSettlementOnchainVerify] =
    useState<SettlementOnchainVerifyResponseDto | null>(null);
  const [acceptedNgh, setAcceptedNgh] = useState<number>(10);
  const [rejectedNgh, setRejectedNgh] = useState<number>(0);
  const [p2SchemaId, setP2SchemaId] = useState('cado_relations@1');
  const [p2VariantMode, setP2VariantMode] = useState<'table' | 'vectors' | 'relations'>('table');
  const [p2Mode, setP2Mode] = useState<QcModeDto>('fp_tolerant');
  const [p2RelTol, setP2RelTol] = useState<number>(1e-4);
  const [p2MaxUlp, setP2MaxUlp] = useState<number>(2);
  const [p2InputA, setP2InputA] = useState('{"i":1,"x":1.0000}\n{"i":2,"x":2.0000}\n');
  const [p2InputB, setP2InputB] = useState('{"i":1,"x":1.0000001}\n{"i":2,"x":2.0}\n');
  const [p2HashA, setP2HashA] = useState<QcHashResponseDto | null>(null);
  const [p2CanonicalA, setP2CanonicalA] = useState<QcCanonicalizeResponseDto | null>(null);
  const [p2CanonicalB, setP2CanonicalB] = useState<QcCanonicalizeResponseDto | null>(null);
  const [p2Compare, setP2Compare] = useState<QcCompareResponseDto | null>(null);
  const [p2Adversarial, setP2Adversarial] = useState<QcAdversarialSuiteResponseDto | null>(null);
  const [p2Matrix, setP2Matrix] = useState<QcAdversarialMatrixResponseDto | null>(null);
  const [p2GoldReport, setP2GoldReport] = useState<QcGoldCorpusEvaluateResponseDto | null>(null);
  const [p2GoldSavedReports, setP2GoldSavedReports] = useState<QcGoldCorpusSavedReportDto[]>([]);
  const [p2GoldLabel, setP2GoldLabel] = useState('P2 benchmark run');
  const [p2PassCriteria, setP2PassCriteria] = useState<QcGoldPassCriteriaDto>({
    min_pass_rate: 0.95,
    max_false_accept_rate: 0.02,
    max_false_reject_rate: 0.05,
  });
  const [p2GoldCasesText, setP2GoldCasesText] = useState(
    JSON.stringify(
      [
        {
          case_id: 'gold-table-pass',
          schema_id: 'table@1',
          mode: 'fp_tolerant',
          rel_tol: 1e-4,
          max_ulp: 2,
          expected_equal: true,
          a_rows: [{ id: 'a', x: 1.0 }],
          b_rows: [{ id: 'a', x: 1.0000000000000002 }],
        },
        {
          case_id: 'gold-table-fail',
          schema_id: 'table@1',
          mode: 'fp_tolerant',
          rel_tol: 1e-4,
          max_ulp: 2,
          expected_equal: false,
          a_rows: [{ id: 'a', x: 1.2 }],
          b_rows: [{ id: 'a', x: 1.5 }],
        },
      ],
      null,
      2,
    ),
  );
  const [p2CaseId, setP2CaseId] = useState<string>(P2_CORPUS[0].id);
  const [p2CorpusResults, setP2CorpusResults] = useState<P2CorpusResult[]>([]);
  const latestReceipt = jobReceipts?.receipts[0] ?? null;
  const latestRunFactoringSummary = firstProviderFactoringSummary(lastDemoRun);
  const latestReceiptProviderSummaries = useMemo(() => {
    const payload = latestReceipt?.payload as Record<string, unknown> | undefined;
    const execs = payload?.provider_executions;
    if (!Array.isArray(execs)) return [] as Record<string, unknown>[];
    return execs
      .map((row) => {
        if (!row || typeof row !== 'object') return null;
        const summary = (row as { factoring_summary?: unknown }).factoring_summary;
        return summary && typeof summary === 'object' ? (summary as Record<string, unknown>) : null;
      })
      .filter((row): row is Record<string, unknown> => row != null);
  }, [latestReceipt]);
  const p2GoldCriteriaPass = useMemo(() => {
    if (!p2GoldReport) return null;
    return (
      p2GoldReport.pass_rate >= p2PassCriteria.min_pass_rate &&
      p2GoldReport.false_accept_rate <= p2PassCriteria.max_false_accept_rate &&
      p2GoldReport.false_reject_rate <= p2PassCriteria.max_false_reject_rate
    );
  }, [p2GoldReport, p2PassCriteria]);
  const p2MatrixReady = useMemo(() => {
    if (!p2Matrix) return null;
    return p2Matrix.modes.every((mode) => {
      const metrics = mode.metrics;
      if (!metrics) return false;
      return (
        metrics.expectation_pass_rate >= 1 &&
        metrics.false_accept_count === 0 &&
        metrics.false_reject_count === 0
      );
    });
  }, [p2Matrix]);
  const p2AdversarialReady = useMemo(() => {
    if (!p2Adversarial?.metrics) return null;
    return (
      p2Adversarial.metrics.expectation_pass_rate >= 1 &&
      p2Adversarial.metrics.false_accept_count === 0 &&
      p2Adversarial.metrics.false_reject_count === 0
    );
  }, [p2Adversarial]);
  const p2PresentationReady = useMemo(() => {
    if (
      p2MatrixReady == null ||
      p2AdversarialReady == null ||
      p2GoldCriteriaPass == null
    ) {
      return null;
    }
    return p2MatrixReady && p2AdversarialReady && p2GoldCriteriaPass;
  }, [p2AdversarialReady, p2GoldCriteriaPass, p2MatrixReady]);

  useEffect(() => {
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

  useEffect(() => {
    let cancelled = false;
    async function syncMarketPrice() {
      try {
        const pk = productKey;
        const [book, tape] = await Promise.all([
          MarketApi.getLiveOrderBook({ ...pk, gpu_model: selectedGPU }),
          MarketApi.getLiveTape({ ...pk, gpu_model: selectedGPU, limit: 60 }),
        ]);
        let px: number | null = null;
        if (tape.length) px = tape[0].price_per_ngh;
        else if (book.best_bid != null && book.best_ask != null) px = (book.best_bid + book.best_ask) / 2;
        else if (book.best_bid != null) px = book.best_bid;
        else if (book.best_ask != null) px = book.best_ask;
        if (!cancelled && px != null && px > 0) {
          setPricePerNgh(Number(px.toFixed(4)));
        }
      } catch {
        /* keep last price */
      }
    }
    void syncMarketPrice();
    const id = globalThis.setInterval(() => void syncMarketPrice(), 5000);
    return () => {
      cancelled = true;
      globalThis.clearInterval(id);
    };
  }, [productKey, selectedGPU]);

  const contractHorizonSeconds = useMemo(
    () => horizonToSeconds(contractHorizonAmount, contractHorizonUnit),
    [contractHorizonAmount, contractHorizonUnit],
  );
  const contractHorizonSecondsRef = useRef(contractHorizonSeconds);
  contractHorizonSecondsRef.current = contractHorizonSeconds;

  const defaultCompositeDigitCount = useMemo(() => {
    const t = deliveryComposite.trim();
    if (!/^\d+$/.test(t)) return 0;
    return t.length;
  }, [deliveryComposite]);

  function compositeExceedsDevStub(composite: string): boolean {
    const max = gpuBackend?.dev_stub_max_composite_digits;
    if (gpuBackend?.factor_backend_kind !== 'dev_remote_factor_server' || max == null) return false;
    const t = composite.trim();
    if (!/^\d+$/.test(t)) return false;
    return t.length > max;
  }

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

  useEffect(() => {
    const t = globalThis.setInterval(() => setPositionClockNowMs(Date.now()), 1000);
    return () => globalThis.clearInterval(t);
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
    void loadGoldCorpusReports(10).catch(() => {
      // Keep panel usable even if report history is temporarily unavailable.
    });
  }, []);

  useEffect(() => {
    const selectedJobId = jobId.trim();
    if (!selectedJobId) {
      setActiveSession(null);
      setJobReceipts(null);
      return;
    }
    void refreshP1State(selectedJobId).catch(() => {
      // Keep panel interactive if these optional reads fail during startup/race.
    });
  }, [jobId]);

  async function run(action: () => Promise<void>) {
    setIsBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
      if (jobId.trim()) {
        await refreshP1State(jobId.trim()).catch(() => {
          // Keep UX responsive when receipts/session fetch is temporarily unavailable.
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function refreshP1State(candidateJobId?: string) {
    const selectedJobId = (candidateJobId ?? jobId).trim();
    if (!selectedJobId) return;
    const [sessions, receipts] = await Promise.all([
      SessionApi.listSessions(selectedJobId),
      JobApi.getReceipts(selectedJobId),
    ]);
    setActiveSession(sessions[0] ?? null);
    setJobReceipts(receipts);
  }

  function loadP2Case(caseId: string) {
    const row = P2_CORPUS.find((c) => c.id === caseId);
    if (!row) return;
    setP2CaseId(row.id);
    setP2SchemaId(row.schemaId);
    setP2Mode(row.mode);
    setP2RelTol(row.relTol ?? 1e-4);
    setP2MaxUlp(row.maxUlp ?? 2);
    setP2InputA(row.inputA);
    setP2InputB(row.inputB);
    setP2Compare(null);
    setP2CanonicalA(null);
    setP2CanonicalB(null);
    setP2HashA(null);
    setStatus(`Loaded P2 case: ${row.title}`);
  }

  async function runP2Corpus() {
    const results: P2CorpusResult[] = [];
    for (const row of P2_CORPUS) {
      let observedEqual = false;
      let detail = '';
      if (row.strategy === 'compare') {
        const res = await QcApi.compare({
          schema_id: row.schemaId,
          mode: row.mode,
          a: row.inputA,
          b: row.inputB,
          rel_tol: row.relTol,
          max_ulp: row.maxUlp,
        });
        observedEqual = res.equal;
        detail = `differences=${res.summary.differences}, rel_err_max=${res.summary.rel_err_max}, ulp_max=${res.summary.ulp_max}`;
      } else {
        const [aCanon, bCanon] = await Promise.all([
          QcApi.canonicalize({
            schema_id: row.schemaId,
            body: row.inputA,
            input_format: row.inputFormatA ?? 'jsonl',
          }),
          QcApi.canonicalize({
            schema_id: row.schemaId,
            body: row.inputB,
            input_format: row.inputFormatB ?? 'jsonl',
          }),
        ]);
        observedEqual = aCanon.merkle_root === bCanon.merkle_root;
        detail = `root_a=${aCanon.merkle_root.slice(0, 12)}..., root_b=${bCanon.merkle_root.slice(0, 12)}...`;
      }
      results.push({
        id: row.id,
        title: row.title,
        expectedEqual: row.expectEqual,
        observedEqual,
        passed: observedEqual === row.expectEqual,
        detail,
      });
    }
    setP2CorpusResults(results);
    const passCount = results.filter((r) => r.passed).length;
    setStatus(`P2 corpus complete: ${passCount}/${results.length} cases passed`);
  }

  async function loadGoldCorpusReports(limit = 10): Promise<number> {
    const rows = await QcApi.listGoldCorpusReports(limit);
    setP2GoldSavedReports(rows.reports);
    return rows.count;
  }

  function parseGoldCasesInput(): QcGoldCorpusCaseDto[] {
    const parsed = JSON.parse(p2GoldCasesText) as QcGoldCorpusCaseDto[];
    if (!Array.isArray(parsed) || parsed.length === 0) {
      throw new Error('Gold corpus JSON must be a non-empty array.');
    }
    return parsed;
  }

  function compositeForPosition(positionId: string): string {
    const override = compositeByPosition[positionId];
    if (override != null && override.trim() !== '') return override.trim();
    return deliveryComposite.trim();
  }

  async function loadExecutionPreflight(positionId: string, candidateJobId?: string) {
    const selectedJobId = (candidateJobId ?? jobId).trim();
    if (!selectedJobId) {
      throw new Error('Enter a job ID first.');
    }
    const report = await MarketApi.getExecutionPreflight(positionId, selectedJobId);
    setPreflightByPosition((prev) => ({ ...prev, [positionId]: report }));
    if (!report.ready_to_execute) {
      throw new Error(`Execution blocked: ${report.reasons.join(' | ')}`);
    }
    return report;
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
                Execution calls your CADO server (<code className="text-slate-300">remote_factor_server</code>). This
                checks that CoreIndex can open a TCP connection to the URL you configured in{' '}
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
          <div className="text-sm text-cyan-200">Execution controls</div>
          <p className="text-xs text-cyan-100/80">
            Trade first, settle to vouchers, escrow to a job, then execute. CADO-NFS still runs on matched
            GPUs across providers; this panel follows the production trading path.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1 sm:col-span-2">
              <div className="text-xs font-medium text-cyan-200/90">Contract horizon</div>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  type="number"
                  min={contractHorizonUnit === 'seconds' ? 30 : 1}
                  max={
                    contractHorizonUnit === 'seconds'
                      ? MAX_TARGET_SETTLE_SECONDS
                      : contractHorizonUnit === 'minutes'
                        ? Math.floor(MAX_TARGET_SETTLE_SECONDS / 60)
                        : contractHorizonUnit === 'days'
                          ? 366
                          : 12
                  }
                  step={1}
                  value={contractHorizonAmount}
                  onChange={(e) => setContractHorizonAmount(Number(e.target.value))}
                  className="w-28 bg-slate-950 border-cyan-900/50 text-sm"
                  aria-label="Horizon amount"
                />
                <Select value={contractHorizonUnit} onValueChange={(v) => setContractHorizonUnit(v as HorizonUnit)}>
                  <SelectTrigger className="w-[11rem] bg-slate-950 border-cyan-900/50 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="seconds">Seconds</SelectItem>
                    <SelectItem value="minutes">Minutes</SelectItem>
                    <SelectItem value="days">Days</SelectItem>
                    <SelectItem value="months">Months (30d each)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="text-[10px] text-cyan-100/60">
                Horizon: {contractHorizonSeconds.toLocaleString()}s (
                {contractHorizonUnit === 'months' ? 'months are 30-day periods' : 'min 30s, max ~366 days'}).
              </div>
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-cyan-200/90">Number to factor</div>
            <Input
              value={deliveryComposite}
              onChange={(e) => setDeliveryComposite(e.target.value)}
              className="bg-slate-950 border-cyan-900/50 font-mono text-sm"
              placeholder="Digits only, e.g. 143"
              aria-label="Composite integer for execution"
            />
            {!validComposite(deliveryComposite) ? (
              <div className="text-[11px] text-amber-200/90">Enter at least two digits (no spaces or letters).</div>
            ) : null}
            {validComposite(deliveryComposite) && defaultCompositeDigitCount > 0 ? (
              <div className="text-[11px] text-slate-400">
                {defaultCompositeDigitCount} digit{defaultCompositeDigitCount === 1 ? '' : 's'} —{' '}
                {gpuBackend?.dev_stub_max_composite_digits != null &&
                defaultCompositeDigitCount > gpuBackend.dev_stub_max_composite_digits ? (
                  <span className="text-amber-200/95">
                    exceeds configured backend limit ({gpuBackend.dev_stub_max_composite_digits} digits); shorten the
                    composite or raise DEV_STUB_MAX_COMPOSITE_DIGITS on the factor service.
                  </span>
                ) : (
                  <span>within the configured backend digit limit.</span>
                )}
              </div>
            ) : null}
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
                const horizonSec = Math.min(
                  MAX_TARGET_SETTLE_SECONDS,
                  Math.max(0, Math.floor(Number(contractHorizonSecondsRef.current))),
                );
                const position = await MarketApi.createPosition({
                  product_key: productKey,
                  side: 'buy',
                  quantity_ngh: quantityNgh,
                  price_per_ngh: pricePerNgh,
                  close_in_seconds: horizonSec > 0 ? horizonSec : 30,
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
                (() => {
                  const secondsUntilClose = positionSecondsUntilClose(
                    position,
                    positionClockNowMs,
                  );
                  const contractClosed = positionContractClosed(position, positionClockNowMs);
                  const preflight = preflightByPosition[position.position_id];
                  return (
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
                          {typeof position.close_in_seconds === 'number' ? (
                            <div className="text-[11px] text-slate-500">
                              Requested close window: {position.close_in_seconds.toLocaleString()}s
                            </div>
                          ) : null}
                          <div className="text-[11px] text-slate-400">
                            Horizon close:{' '}
                            {contractClosed ? (
                              <span className="text-emerald-300">closed</span>
                            ) : (
                              <span className="text-amber-300">{secondsUntilClose}s remaining</span>
                            )}
                          </div>
                            {!contractClosed ? (
                              <div className="text-[11px] text-amber-200/90">
                                Trading-only window: settlement, preflight, execution, and voucher escrow stay locked
                                until close.
                              </div>
                            ) : null}
                        </div>

                        <div className="flex flex-col gap-3 lg:flex-1 lg:min-w-0">
                          <div className="space-y-1">
                            <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
                              Number to factor (this contract)
                            </div>
                            <Input
                              value={compositeByPosition[position.position_id] ?? ''}
                              onChange={(e) =>
                                setCompositeByPosition((prev) => ({
                                  ...prev,
                                  [position.position_id]: e.target.value,
                                }))
                              }
                              placeholder={deliveryComposite || 'e.g. 143'}
                              className="bg-slate-800 border-slate-700 font-mono text-xs h-8"
                              aria-label={`Composite to factor for position ${position.position_id}`}
                            />
                            <div className="text-[10px] text-slate-500">
                              Leave blank to use the default under &quot;Deposit vouchers&quot; (
                              {validComposite(deliveryComposite) ? deliveryComposite : 'set a valid default'}).
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center gap-3">
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
                              title={!contractClosed ? 'Can settle only after the futures close horizon.' : undefined}
                              disabled={isBusy || position.status === 'settled' || !contractClosed}
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
                              className="bg-cyan-600 hover:bg-cyan-700"
                              title={
                                !contractClosed
                                  ? `Contract has not closed yet (${secondsUntilClose}s remaining).`
                                  : compositeExceedsDevStub(compositeForPosition(position.position_id))
                                    ? `Composite exceeds dev stub max (${gpuBackend?.dev_stub_max_composite_digits ?? '?'} digits). Use CADO backend or a shorter N.`
                                    : undefined
                              }
                              disabled={
                                isBusy ||
                                !jobId.trim() ||
                                !contractClosed ||
                                !validComposite(compositeForPosition(position.position_id)) ||
                                compositeExceedsDevStub(compositeForPosition(position.position_id))
                              }
                              onClick={() =>
                                void run(async () => {
                                  await loadExecutionPreflight(position.position_id, jobId);
                                  const result = await MarketApi.executeContract(position.position_id, {
                                    job_id: jobId.trim(),
                                    composite: compositeForPosition(position.position_id),
                                    target_settle_seconds: contractHorizonSeconds,
                                    auto_settle_if_open: false,
                                  });
                                  setLastDemoRun(result);
                                  setStatus(
                                    `Execution complete · tx ${result.blockchain_anchor.tx_hash.slice(0, 12)}... · verification ${result.verification_passed ? 'passed' : 'failed'}`,
                                  );
                                })
                              }
                            >
                              Execute Contract (CADO-NFS)
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="border-slate-700 bg-slate-900"
                              title={!contractClosed ? 'Preflight is available only after close horizon.' : undefined}
                              disabled={isBusy || !jobId.trim() || !contractClosed}
                              onClick={() =>
                                void run(async () => {
                                  const report = await loadExecutionPreflight(position.position_id, jobId);
                                  setStatus(
                                    report.ready_to_execute
                                      ? `Preflight passed · ${report.matching_provider_count} providers · ${report.total_available_gpus} GPUs visible`
                                      : `Preflight failed · ${report.reasons.join(' | ')}`,
                                  );
                                })
                              }
                            >
                              Run Preflight
                            </Button>
                          </div>
                          {preflight ? (
                            <div className="rounded border border-slate-800/80 bg-slate-950/40 p-2 text-[11px]">
                              <div className="space-y-1 text-slate-400">
                                <div>
                                  <span className="text-slate-500">Preflight: </span>
                                  <span className={preflight.ready_to_execute ? 'text-emerald-300' : 'text-amber-300'}>
                                    {preflight.ready_to_execute ? 'ready' : 'blocked'}
                                  </span>
                                  <span className="text-slate-500"> · Escrowed </span>
                                  {preflight.deposited_ngh.toFixed(2)} / required {preflight.required_ngh.toFixed(2)} NGH
                                </div>
                                {!preflight.ready_to_execute ? (
                                  <div className="text-amber-200/90">{preflight.reasons.join(' | ')}</div>
                                ) : null}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                })()
              ))
            ) : (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
                No positions yet. Buy exposure to start the futures-to-vouchers flow.
              </div>
            )}
          </div>
        </div>
      </Card>

      <div className="space-y-4">
        <div className="rounded-lg border border-slate-700/80 bg-slate-950/60 p-4 text-xs text-slate-300 space-y-2">
          <div className="text-sm font-medium text-slate-100">How to use this column</div>
          <ol className="list-decimal list-inside space-y-1.5 text-slate-400 leading-relaxed">
            <li>
              <span className="text-slate-200">Wallet &amp; job</span> — align the job with the same product key as
              your contract, deposit escrow from the matching voucher wallet.
            </li>
            <li>
              <span className="text-slate-200">Commodity matching</span> — sellers are market-assigned at execution;
              buyers never pin a specific listing.
            </li>
            <li>
              <span className="text-slate-200">Execute</span> lives on the left under each open position (after
              deposit).
            </li>
            <li>
              <span className="text-slate-200">Settlement</span> — optional collective session, QC shortcuts, anchor /
              pay / on-chain verify (demo chain).
            </li>
            <li>
              <span className="text-slate-200">P2 QC lab</span> — separate canonicalization benchmarks; not required for
              delivery execution.
            </li>
          </ol>
        </div>

        <Tabs defaultValue="wallet" className="w-full">
          <TabsList className="grid h-auto w-full grid-cols-3 gap-1 border border-slate-800 bg-slate-900 p-1">
            <TabsTrigger value="wallet" className="px-1 py-2 text-[11px] leading-tight">
              Wallet &amp; job
            </TabsTrigger>
            <TabsTrigger value="settlement" className="px-1 py-2 text-[11px] leading-tight">
              Settlement
            </TabsTrigger>
            <TabsTrigger value="p2" className="px-1 py-2 text-[11px] leading-tight">
              P2 QC lab
            </TabsTrigger>
          </TabsList>

          <TabsContent value="wallet" className="mt-4 space-y-6">
        <Card className="bg-slate-900 border-slate-800 p-6">
          <div className="text-slate-100">Voucher balances</div>
          <div className="mt-3 h-72 overflow-y-scroll overscroll-contain space-y-3 pr-2">
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
              Execution now uses strict preflight checks: job must exist, the job key must match this
              contract key, and escrowed vouchers must cover required NGH before compute starts.
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
              variant="outline"
              className="w-full border-slate-700 bg-slate-900"
              disabled={isBusy}
              onClick={() =>
                void run(async () => {
                  const generated = `job-${Date.now()}`;
                  const created = await JobApi.createJob({
                    job_id: generated,
                    window: productKey,
                    package_index: [
                      {
                        package_id: `pkg-${Math.random().toString(36).slice(2, 10)}`,
                        size_estimate_ngh: 10,
                        first_output_estimate_seconds: 60,
                        metadata: { gpu_name: selectedGPU, flow: 'trader-path' },
                      },
                    ],
                  });
                  setJobId(created.job_id);
                  setStatus(`Created job ${created.job_id} for ${formatProductKey(created.window)}`);
                })
              }
            >
              Create Job for Current Key
            </Button>
            <Button
              className="w-full bg-violet-600 hover:bg-violet-700"
              title={
                positions.some((p) => {
                  if (p.status === 'settled') return false;
                  if (!productKeysEqual(p.product_key, productKey)) return false;
                  return !positionContractClosed(p, positionClockNowMs);
                })
                  ? 'Cannot escrow vouchers while any open futures contract for this product key is still inside its close window (including legacy rows without closes_at).'
                  : undefined
              }
              disabled={
                isBusy ||
                !jobId.trim() ||
                positions.some((p) => {
                  if (p.status === 'settled') return false;
                  if (!productKeysEqual(p.product_key, productKey)) return false;
                  return !positionContractClosed(p, positionClockNowMs);
                })
              }
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
            <div className="text-xs text-slate-500">Default composite for execution and any position row left blank.</div>
            <Input
              value={deliveryComposite}
              onChange={(e) => setDeliveryComposite(e.target.value)}
              className="bg-slate-800 border-slate-700 font-mono"
              placeholder="e.g. 143 (11×13) for a quick GPU check"
            />
            <div className="text-xs text-slate-500">
              Provider pairing and GPU count are matched by the market at execution; you choose N to factor per contract
              above or override on each open position card.
            </div>
          </div>
        </Card>
          </TabsContent>

          <TabsContent value="settlement" className="mt-4 space-y-6">
        <Card className="bg-slate-900 border-slate-800 p-6">
          <div className="text-slate-100">P1 Operations: Sessions, QC, Settlement</div>
          <p className="mt-2 text-xs text-slate-400">
            Optional post-execution steps tied to the <span className="text-slate-200">Job ID</span> from the Wallet
            tab. Nothing here blocks CADO execution — use it when you want session records, QC attestations, or a
            settlement anchor on the demo chain.
          </p>
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 space-y-3">
              <div className="text-sm text-slate-200">Collective session</div>
              <label className="block space-y-1 text-[11px] text-slate-400">
                Session ID
                <Input
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                  placeholder={jobId.trim() ? `sess-${jobId.trim()}` : 'sess-job-123'}
                  className="bg-slate-800 border-slate-700"
                  autoComplete="off"
                />
              </label>
              <label className="block space-y-1 text-[11px] text-slate-400">
                Members (comma-separated)
                <Input
                  value={sessionMembershipCsv}
                  onChange={(e) => setSessionMembershipCsv(e.target.value)}
                  placeholder="member-a,member-b"
                  className="bg-slate-800 border-slate-700"
                  autoComplete="off"
                />
              </label>
              <label className="block space-y-1 text-[11px] text-slate-400">
                World size (≥ number of members)
                <Input
                  type="number"
                  min={1}
                  value={sessionWorldSize}
                  onChange={(e) => setSessionWorldSize(Math.max(1, Number(e.target.value) || 1))}
                  className="bg-slate-800 border-slate-700"
                />
              </label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Button
                  size="sm"
                  className="bg-cyan-700 hover:bg-cyan-800"
                  disabled={isBusy || !jobId.trim()}
                  onClick={() =>
                    void run(async () => {
                      const members = sessionMembershipCsv
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean);
                      const sid = sessionId.trim() || `sess-${jobId.trim()}`;
                      const created = await SessionApi.createSession({
                        session_id: sid,
                        job_id: jobId.trim(),
                        ...productKey,
                        world_size: Math.max(sessionWorldSize, members.length || 1),
                        membership: members.length ? members : ['member-a'],
                      });
                      setSessionId(created.session_id);
                      setActiveSession(created);
                      setStatus(`Session created: ${created.session_id}`);
                    })
                  }
                >
                  Create session
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-slate-700 bg-slate-900"
                  disabled={isBusy || !sessionId.trim()}
                  onClick={() =>
                    void run(async () => {
                      await SessionApi.finalizeSession(sessionId.trim());
                      await refreshP1State(jobId);
                      setStatus(`Session finalized: ${sessionId.trim()}`);
                    })
                  }
                >
                  Finalize
                </Button>
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_auto]">
                <label className="min-w-0 space-y-1 text-[11px] text-slate-400 sm:col-span-1">
                  Member to mark ready
                  <Input
                    value={sessionReadyMember}
                    onChange={(e) => setSessionReadyMember(e.target.value)}
                    placeholder="member-a"
                    className="bg-slate-800 border-slate-700"
                    autoComplete="off"
                  />
                </label>
                <Button
                  size="sm"
                  className="bg-emerald-700 hover:bg-emerald-800"
                  disabled={isBusy || !sessionId.trim() || !sessionReadyMember.trim()}
                  onClick={() =>
                    void run(async () => {
                      const row = await SessionApi.markReady(sessionId.trim(), sessionReadyMember.trim());
                      setActiveSession(row);
                      setStatus(`Ready attested: ${sessionReadyMember.trim()} (${row.ready_count}/${row.world_size})`);
                    })
                  }
                >
                  Mark ready
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-slate-700 bg-slate-900"
                  disabled={isBusy || !jobId.trim()}
                  onClick={() =>
                    void run(async () => {
                      await refreshP1State(jobId);
                      setStatus(`Loaded session state for ${jobId.trim()}`);
                    })
                  }
                >
                  Reload
                </Button>
              </div>
              {activeSession ? (
                <div className="rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-400">
                  <div>
                    <span className="text-slate-500">Session:</span> {activeSession.session_id}
                  </div>
                  <div>
                    <span className="text-slate-500">State:</span> {activeSession.state}
                  </div>
                  <div>
                    <span className="text-slate-500">Ready:</span> {activeSession.ready_count}/{activeSession.world_size}
                  </div>
                  <div>
                    <span className="text-slate-500">Members:</span> {activeSession.membership.join(', ')}
                  </div>
                  <div>
                    <span className="text-slate-500">Ready members:</span>{' '}
                    {activeSession.ready_members.length ? activeSession.ready_members.join(', ') : 'none yet'}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-4 space-y-3">
              <div className="text-sm text-slate-200">QC + settlement</div>
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Package ID usually matches a job package (see job detail). Receipt / QC roots default to demo hex —
                click <span className="text-slate-300">Use latest receipt hash</span> after execution to align with
                the last delivery receipt.
              </p>
              <label className="block space-y-1 text-[11px] text-slate-400">
                Package ID
                <Input
                  value={qcPackageId}
                  onChange={(e) => setQcPackageId(e.target.value)}
                  placeholder="pkg-…"
                  className="bg-slate-800 border-slate-700"
                  autoComplete="off"
                />
              </label>
              <label className="block space-y-1 text-[11px] text-slate-400">
                Provider ID (optional)
                <Input
                  value={qcProviderId}
                  onChange={(e) => setQcProviderId(e.target.value)}
                  placeholder="provider-1"
                  className="bg-slate-800 border-slate-700"
                  autoComplete="off"
                />
              </label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="border-slate-700 bg-slate-900"
                  disabled={isBusy || !jobId.trim() || !qcPackageId.trim()}
                  onClick={() =>
                    void run(async () => {
                      await QcApi.submitDuplicate({
                        job_id: jobId.trim(),
                        package_id: qcPackageId.trim(),
                        provider_id: qcProviderId.trim() || undefined,
                        verdict: 'pass',
                        detail: 'UI duplicate check pass',
                      });
                      setStatus(`QC duplicate recorded for ${qcPackageId.trim()}`);
                    })
                  }
                >
                  QC duplicate
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-slate-700 bg-slate-900"
                  disabled={isBusy || !jobId.trim() || !qcPackageId.trim()}
                  onClick={() =>
                    void run(async () => {
                      await QcApi.submitSpot({
                        job_id: jobId.trim(),
                        package_id: qcPackageId.trim(),
                        provider_id: qcProviderId.trim() || undefined,
                        verdict: 'pass',
                        detail: 'UI spot check pass',
                      });
                      setStatus(`QC spot recorded for ${qcPackageId.trim()}`);
                    })
                  }
                >
                  QC spot
                </Button>
              </div>
              <label className="block space-y-1 text-[11px] text-slate-400">
                Receipt Merkle root (hex)
                <Input
                  value={receiptRoot}
                  onChange={(e) => setReceiptRoot(e.target.value)}
                  placeholder="0x…"
                  className="bg-slate-800 border-slate-700 font-mono"
                  autoComplete="off"
                />
              </label>
              <label className="block space-y-1 text-[11px] text-slate-400">
                QC Merkle root (hex)
                <Input
                  value={qcRoot}
                  onChange={(e) => setQcRoot(e.target.value)}
                  placeholder="0x…"
                  className="bg-slate-800 border-slate-700 font-mono"
                  autoComplete="off"
                />
              </label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Button
                  size="sm"
                  className="bg-violet-700 hover:bg-violet-800"
                  disabled={isBusy || !jobId.trim() || !receiptRoot.trim() || !qcRoot.trim()}
                  onClick={() =>
                    void run(async () => {
                      const anchored = await SettlementApi.anchor({
                        job_id: jobId.trim(),
                        receipt_root: receiptRoot.trim(),
                        qc_root: qcRoot.trim(),
                        note: 'anchored from market panel',
                      });
                      setSettlementRun(anchored);
                      setSettlementOnchainVerify(null);
                      setStatus(`Settlement anchored: ${anchored.settlement_id}`);
                    })
                  }
                >
                  Anchor settlement
                </Button>
                <Button
                  size="sm"
                  className="bg-emerald-700 hover:bg-emerald-800"
                  disabled={isBusy || !jobId.trim() || !settlementRun?.settlement_id}
                  onClick={() =>
                    void run(async () => {
                      const settled = await SettlementApi.pay({
                        job_id: jobId.trim(),
                        settlement_id: settlementRun!.settlement_id,
                        accepted_ngh: acceptedNgh,
                        rejected_ngh: rejectedNgh,
                      });
                      setSettlementRun(settled);
                      setStatus(`Settlement paid: ${settled.settlement_id} (${settled.state})`);
                    })
                  }
                >
                  Pay settlement
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="border-slate-700 bg-slate-900"
                  disabled={isBusy || !settlementRun?.settlement_id}
                  onClick={() =>
                    void run(async () => {
                      const verify = await SettlementApi.verifyOnchain(settlementRun!.settlement_id);
                      setSettlementOnchainVerify(verify);
                      setStatus(
                        verify.verified
                          ? `On-chain verification passed · tx ${verify.tx_hash?.slice(0, 12) ?? 'n/a'}...`
                          : `On-chain verification failed · ${verify.reason ?? 'unknown reason'}`,
                      );
                    })
                  }
                >
                  Verify on-chain anchor
                </Button>
              </div>
              {latestReceipt?.verification_hash ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="border-slate-700 bg-slate-900"
                  disabled={isBusy}
                  onClick={() => {
                    setReceiptRoot(latestReceipt.verification_hash ?? receiptRoot);
                    setStatus('Loaded receipt root from latest receipt verification hash');
                  }}
                >
                  Use latest receipt hash as root
                </Button>
              ) : null}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Input
                  type="number"
                  min={0}
                  value={acceptedNgh}
                  onChange={(e) => setAcceptedNgh(Math.max(0, Number(e.target.value) || 0))}
                  className="bg-slate-800 border-slate-700"
                  placeholder="accepted ngh"
                />
                <Input
                  type="number"
                  min={0}
                  value={rejectedNgh}
                  onChange={(e) => setRejectedNgh(Math.max(0, Number(e.target.value) || 0))}
                  className="bg-slate-800 border-slate-700"
                  placeholder="rejected ngh"
                />
              </div>
              {settlementRun ? (
                <div className="rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-400">
                  <div>
                    <span className="text-slate-500">Settlement:</span> {settlementRun.settlement_id}
                  </div>
                  <div>
                    <span className="text-slate-500">State:</span> {settlementRun.state}
                  </div>
                  <div>
                    <span className="text-slate-500">Accepted/Rejected:</span> {settlementRun.accepted_ngh} /{' '}
                    {settlementRun.rejected_ngh} NGH
                  </div>
                  {settlementRun.anchor_hash ? (
                    <div className="font-mono break-all">
                      <span className="text-slate-500">Anchor hash:</span> {settlementRun.anchor_hash}
                    </div>
                  ) : null}
                  {settlementRun.blockchain_anchor?.tx_hash ? (
                    <div className="font-mono break-all">
                      <span className="text-slate-500">Tx hash:</span> {settlementRun.blockchain_anchor.tx_hash}
                    </div>
                  ) : null}
                  {settlementOnchainVerify ? (
                    <div>
                      <span className="text-slate-500">On-chain verify:</span>{' '}
                      <span
                        className={
                          settlementOnchainVerify.verified ? 'text-emerald-300' : 'text-amber-300'
                        }
                      >
                        {settlementOnchainVerify.verified ? 'verified' : 'not verified'}
                      </span>
                      {settlementOnchainVerify.reason ? ` · ${settlementOnchainVerify.reason}` : ''}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/40 p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm text-slate-200">Receipt bundle</div>
              <Button
                size="sm"
                variant="outline"
                className="border-slate-700 bg-slate-900"
                disabled={isBusy || !jobId.trim()}
                onClick={() =>
                  void run(async () => {
                    await refreshP1State(jobId);
                    setStatus(`Loaded receipts for ${jobId.trim()}`);
                  })
                }
              >
                Load receipts
              </Button>
            </div>
            {jobReceipts ? (
              <div className="text-xs text-slate-400">
                <div>
                  <span className="text-slate-500">Count:</span> {jobReceipts.receipt_count}
                </div>
                <div className="mt-2 max-h-28 overflow-y-auto overscroll-contain space-y-1 pr-1">
                  {jobReceipts.receipts.length ? (
                    jobReceipts.receipts.map((row) => (
                      <div key={row.event_id} className="rounded border border-slate-800/80 px-2 py-1">
                        <div className="font-mono text-[10px] text-slate-500">{row.event_id.slice(0, 16)}...</div>
                        <div>
                          providers {row.provider_count} · delivered {row.delivered_ngh.toFixed(2)} NGH
                          {row.settlement_status ? ` · ${row.settlement_status}` : ''}
                        </div>
                        {row.verification_hash ? (
                          <div className="font-mono text-[10px] text-slate-500 break-all">
                            {row.verification_hash}
                          </div>
                        ) : null}
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-500">No receipts yet for this job.</div>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-500">Choose a job and load receipts.</div>
            )}
          </div>
        </Card>
          </TabsContent>

          <TabsContent value="p2" className="mt-4 space-y-6">
        <Card className="bg-slate-900 border-slate-800 p-6">
          <div className="text-slate-100">P2 Verification: Canonicalization & Equivalence</div>
          <p className="mt-2 text-xs text-slate-400">
            Validate schema-aware hashing and comparison behavior across small output variations. This is the
            cross-arch correctness surface for duplicate and spot checks.
          </p>
          <div className="mt-3 rounded border border-slate-800/80 bg-slate-950/30 p-3 text-[11px] text-slate-300">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-slate-200">P2 presentation readiness</div>
              <Button
                size="sm"
                className="bg-emerald-700 hover:bg-emerald-800"
                disabled={isBusy || !p2SchemaId.trim() || !p2InputA.trim() || !p2GoldCasesText.trim()}
                onClick={() =>
                  void run(async () => {
                    const baseRows = parseJsonlRows(p2InputA);
                    const [suite, matrix, report] = await Promise.all([
                      QcApi.runAdversarialSuite({
                        schema_id: p2SchemaId.trim(),
                        mode: p2Mode,
                        rel_tol: p2RelTol,
                        max_ulp: p2MaxUlp,
                        variant_mode: p2VariantMode,
                        base_rows: baseRows,
                      }),
                      QcApi.runAdversarialMatrix({
                        schema_id: p2SchemaId.trim(),
                        rel_tol: p2RelTol,
                        max_ulp: p2MaxUlp,
                        variant_mode: p2VariantMode,
                        base_rows: baseRows,
                      }),
                      QcApi.evaluateGoldCorpus({ cases: parseGoldCasesInput() }),
                    ]);
                    setP2Adversarial(suite);
                    setP2Matrix(matrix);
                    setP2GoldReport(report);
                    const matrixOk = matrix.modes.every((m) => {
                      const metrics = m.metrics;
                      return (
                        !!metrics &&
                        metrics.expectation_pass_rate >= 1 &&
                        metrics.false_accept_count === 0 &&
                        metrics.false_reject_count === 0
                      );
                    });
                    const adversarialOk =
                      (suite.metrics?.expectation_pass_rate ?? 0) >= 1 &&
                      (suite.metrics?.false_accept_count ?? 0) === 0 &&
                      (suite.metrics?.false_reject_count ?? 0) === 0;
                    const goldOk =
                      report.pass_rate >= p2PassCriteria.min_pass_rate &&
                      report.false_accept_rate <= p2PassCriteria.max_false_accept_rate &&
                      report.false_reject_rate <= p2PassCriteria.max_false_reject_rate;
                    setStatus(
                      matrixOk && adversarialOk && goldOk
                        ? 'P2 presentation check passed'
                        : 'P2 presentation check found gaps',
                    );
                  })
                }
              >
                Run presentation check
              </Button>
            </div>
            <div className="mt-2 grid grid-cols-1 gap-1 md:grid-cols-4">
              <div>
                <span className="text-slate-500">Overall:</span>{' '}
                <span
                  className={
                    p2PresentationReady == null
                      ? 'text-slate-300'
                      : p2PresentationReady
                        ? 'text-emerald-300'
                        : 'text-amber-300'
                  }
                >
                  {p2PresentationReady == null ? 'not run' : p2PresentationReady ? 'READY' : 'NOT READY'}
                </span>
              </div>
              <div>
                <span className="text-slate-500">Matrix:</span>{' '}
                <span className={p2MatrixReady == null ? 'text-slate-300' : p2MatrixReady ? 'text-emerald-300' : 'text-amber-300'}>
                  {p2MatrixReady == null ? 'n/a' : p2MatrixReady ? 'PASS' : 'FAIL'}
                </span>
              </div>
              <div>
                <span className="text-slate-500">Adversarial:</span>{' '}
                <span
                  className={
                    p2AdversarialReady == null ? 'text-slate-300' : p2AdversarialReady ? 'text-emerald-300' : 'text-amber-300'
                  }
                >
                  {p2AdversarialReady == null ? 'n/a' : p2AdversarialReady ? 'PASS' : 'FAIL'}
                </span>
              </div>
              <div>
                <span className="text-slate-500">Gold criteria:</span>{' '}
                <span
                  className={
                    p2GoldCriteriaPass == null ? 'text-slate-300' : p2GoldCriteriaPass ? 'text-emerald-300' : 'text-amber-300'
                  }
                >
                  {p2GoldCriteriaPass == null ? 'n/a' : p2GoldCriteriaPass ? 'PASS' : 'FAIL'}
                </span>
              </div>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-5">
            <Input
              value={p2SchemaId}
              onChange={(e) => setP2SchemaId(e.target.value)}
              placeholder="schema id"
              className="bg-slate-800 border-slate-700 md:col-span-2"
            />
            <Select value={p2Mode} onValueChange={(v) => setP2Mode(v as QcModeDto)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="bit_exact">bit_exact</SelectItem>
                <SelectItem value="fp_tolerant">fp_tolerant</SelectItem>
              </SelectContent>
            </Select>
            <Select value={p2VariantMode} onValueChange={(v) => setP2VariantMode(v as 'table' | 'vectors' | 'relations')}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="table">table adversarial set</SelectItem>
                <SelectItem value="vectors">vectors adversarial set</SelectItem>
                <SelectItem value="relations">relations adversarial set</SelectItem>
              </SelectContent>
            </Select>
            <div className="grid grid-cols-2 gap-2">
              <Input
                type="number"
                min={0}
                step={0.000001}
                value={p2RelTol}
                onChange={(e) => setP2RelTol(Math.max(0, Number(e.target.value) || 0))}
                className="bg-slate-800 border-slate-700 text-xs"
                placeholder="rel_tol"
              />
              <Input
                type="number"
                min={0}
                step={1}
                value={p2MaxUlp}
                onChange={(e) => setP2MaxUlp(Math.max(0, Math.floor(Number(e.target.value) || 0)))}
                className="bg-slate-800 border-slate-700 text-xs"
                placeholder="max_ulp"
              />
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-[1fr_auto_auto]">
            <Select value={p2CaseId} onValueChange={(v) => setP2CaseId(v)}>
              <SelectTrigger className="bg-slate-800 border-slate-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {P2_CORPUS.map((row) => (
                  <SelectItem key={row.id} value={row.id}>
                    {row.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              className="border-slate-700 bg-slate-900"
              disabled={isBusy}
              onClick={() => loadP2Case(p2CaseId)}
            >
              Load case
            </Button>
            <Button
              size="sm"
              className="bg-indigo-700 hover:bg-indigo-800"
              disabled={isBusy}
              onClick={() =>
                void run(async () => {
                  await runP2Corpus();
                })
              }
            >
              Run P2 corpus
            </Button>
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            {P2_CORPUS.find((row) => row.id === p2CaseId)?.description ?? ''}
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
            <textarea
              value={p2InputA}
              onChange={(e) => setP2InputA(e.target.value)}
              className="h-32 rounded-md border border-slate-700 bg-slate-950 p-2 text-xs font-mono text-slate-200"
              placeholder="Output A (canonical JSONL)"
            />
            <textarea
              value={p2InputB}
              onChange={(e) => setP2InputB(e.target.value)}
              className="h-32 rounded-md border border-slate-700 bg-slate-950 p-2 text-xs font-mono text-slate-200"
              placeholder="Output B (canonical JSONL)"
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              className="border-slate-700 bg-slate-900"
              disabled={isBusy || !p2InputA.trim()}
              onClick={() =>
                void run(async () => {
                  const h = await QcApi.hashCanonical(p2InputA);
                  setP2HashA(h);
                  setStatus(`P2 hash computed · ${h.merkle_root.slice(0, 12)}...`);
                })
              }
            >
              Hash A
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-slate-700 bg-slate-900"
              disabled={isBusy || !p2SchemaId.trim() || !p2InputA.trim()}
              onClick={() =>
                void run(async () => {
                  const r = await QcApi.canonicalize({
                    schema_id: p2SchemaId.trim(),
                    body: p2InputA,
                    input_format: 'canonical_jsonl',
                  });
                  setP2CanonicalA(r);
                  setStatus(`P2 canonicalized A · root ${r.merkle_root.slice(0, 12)}...`);
                })
              }
            >
              Canonicalize A
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-slate-700 bg-slate-900"
              disabled={isBusy || !p2SchemaId.trim() || !p2InputB.trim()}
              onClick={() =>
                void run(async () => {
                  const r = await QcApi.canonicalize({
                    schema_id: p2SchemaId.trim(),
                    body: p2InputB,
                    input_format: 'canonical_jsonl',
                  });
                  setP2CanonicalB(r);
                  setStatus(`P2 canonicalized B · root ${r.merkle_root.slice(0, 12)}...`);
                })
              }
            >
              Canonicalize B
            </Button>
            <Button
              size="sm"
              className="bg-cyan-700 hover:bg-cyan-800"
              disabled={isBusy || !p2SchemaId.trim() || !p2InputA.trim() || !p2InputB.trim()}
              onClick={() =>
                void run(async () => {
                  const cmp = await QcApi.compare({
                    schema_id: p2SchemaId.trim(),
                    mode: p2Mode,
                    a: p2InputA,
                    b: p2InputB,
                    rel_tol: p2RelTol,
                    max_ulp: p2MaxUlp,
                  });
                  setP2Compare(cmp);
                  setStatus(
                    cmp.equal
                      ? `P2 compare passed · mode ${cmp.mode}`
                      : `P2 compare mismatch · ${cmp.summary.differences} differences`,
                  );
                })
              }
            >
              Compare A vs B
            </Button>
            <Button
              size="sm"
              className="bg-violet-700 hover:bg-violet-800"
              disabled={isBusy || !p2SchemaId.trim() || !p2InputA.trim()}
              onClick={() =>
                void run(async () => {
                  const baseRows = parseJsonlRows(p2InputA);
                  const suite = await QcApi.runAdversarialSuite({
                    schema_id: p2SchemaId.trim(),
                    mode: p2Mode,
                    rel_tol: p2RelTol,
                    max_ulp: p2MaxUlp,
                    variant_mode: p2VariantMode,
                    base_rows: baseRows,
                  });
                  setP2Adversarial(suite);
                  const passed = suite.results.filter((row) => row.expectation_passed).length;
                  setStatus(`P2 adversarial suite: ${passed}/${suite.results.length} expectations passed`);
                })
              }
            >
              Run adversarial suite
            </Button>
            <Button
              size="sm"
              className="bg-fuchsia-700 hover:bg-fuchsia-800"
              disabled={isBusy || !p2SchemaId.trim() || !p2InputA.trim()}
              onClick={() =>
                void run(async () => {
                  const baseRows = parseJsonlRows(p2InputA);
                  const matrix = await QcApi.runAdversarialMatrix({
                    schema_id: p2SchemaId.trim(),
                    rel_tol: p2RelTol,
                    max_ulp: p2MaxUlp,
                    variant_mode: p2VariantMode,
                    base_rows: baseRows,
                  });
                  setP2Matrix(matrix);
                  const allModesPass = matrix.modes.every(
                    (m) => (m.metrics?.expectation_pass_rate ?? 0) >= 1,
                  );
                  setStatus(
                    allModesPass
                      ? 'P2 matrix passed for bit_exact and fp_tolerant'
                      : 'P2 matrix found divergences; inspect mode metrics',
                  );
                })
              }
            >
              Run full matrix
            </Button>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
            <div className="rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-400">
              <div className="text-slate-300">Hash A</div>
              <div className="mt-1 font-mono break-all">{p2HashA?.merkle_root ?? '—'}</div>
            </div>
            <div className="rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-400">
              <div className="text-slate-300">Canonical root A</div>
              <div className="mt-1 font-mono break-all">{p2CanonicalA?.merkle_root ?? '—'}</div>
            </div>
            <div className="rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-400">
              <div className="text-slate-300">Canonical root B</div>
              <div className="mt-1 font-mono break-all">{p2CanonicalB?.merkle_root ?? '—'}</div>
            </div>
          </div>
          {p2Compare ? (
            <div className="mt-3 rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-300">
              <div>
                <span className="text-slate-500">Result:</span>{' '}
                <span className={p2Compare.equal ? 'text-emerald-300' : 'text-amber-300'}>
                  {p2Compare.equal ? 'equivalent' : 'mismatch'}
                </span>
              </div>
              <div>
                <span className="text-slate-500">Differences:</span> {p2Compare.summary.differences}
              </div>
              <div>
                <span className="text-slate-500">rel_err_max:</span> {p2Compare.summary.rel_err_max}
              </div>
              <div>
                <span className="text-slate-500">ulp_max:</span> {p2Compare.summary.ulp_max}
              </div>
            </div>
          ) : null}
          {p2CorpusResults.length ? (
            <div className="mt-3 rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-300">
              <div className="mb-1 text-slate-200">Corpus results</div>
              <div className="max-h-36 overflow-y-auto overscroll-contain space-y-1 pr-1">
                {p2CorpusResults.map((row) => (
                  <div key={row.id} className="rounded border border-slate-800/80 px-2 py-1">
                    <div>
                      <span className={row.passed ? 'text-emerald-300' : 'text-amber-300'}>
                        {row.passed ? 'PASS' : 'FAIL'}
                      </span>{' '}
                      · {row.title}
                    </div>
                    <div className="text-slate-500">
                      expected={row.expectedEqual ? 'equal' : 'mismatch'} · observed=
                      {row.observedEqual ? 'equal' : 'mismatch'}
                    </div>
                    <div className="text-slate-500">{row.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {p2Adversarial ? (
            <div className="mt-3 rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-300">
              <div className="mb-1">
                <span className="text-slate-500">Adversarial mode:</span> {p2Adversarial.variant_mode} ·{' '}
                <span className="text-slate-500">base rows:</span> {p2Adversarial.base_record_count}
              </div>
              {p2Adversarial.metrics ? (
                <div className="mb-2 text-slate-400">
                  pass {(p2Adversarial.metrics.expectation_pass_rate * 100).toFixed(1)}% · false accept{' '}
                  {p2Adversarial.metrics.false_accept_count} · false reject {p2Adversarial.metrics.false_reject_count}
                </div>
              ) : null}
              <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                {p2Adversarial.results.map((row) => (
                  <div key={row.variant} className="rounded border border-slate-800/70 px-2 py-1">
                    <span className="text-slate-200">{row.variant}</span>
                    <span className="text-slate-500"> · equal </span>
                    <span className={row.equal ? 'text-emerald-300' : 'text-amber-300'}>
                      {String(row.equal)}
                    </span>
                    <span className="text-slate-500"> · expected </span>
                    <span className={row.expected_equal ? 'text-emerald-300' : 'text-amber-300'}>
                      {String(row.expected_equal)}
                    </span>
                    <span className="text-slate-500"> · check </span>
                    <span className={row.expectation_passed ? 'text-emerald-300' : 'text-red-300'}>
                      {row.expectation_passed ? 'pass' : 'fail'}
                    </span>
                    <span className="text-slate-500"> · diffs </span>
                    {row.summary.differences ?? 0}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {p2Matrix ? (
            <div className="mt-3 rounded border border-slate-800/80 bg-slate-950/30 p-2 text-[11px] text-slate-300">
              <div className="mb-1 text-slate-200">P2 matrix summary</div>
              <div className="space-y-1">
                {p2Matrix.modes.map((modeReport) => (
                  <div key={modeReport.mode} className="rounded border border-slate-800/70 px-2 py-1">
                    <span className="text-slate-200">{modeReport.mode}</span>
                    <span className="text-slate-500"> · pass </span>
                    {((modeReport.metrics?.expectation_pass_rate ?? 0) * 100).toFixed(1)}%
                    <span className="text-slate-500"> · FA </span>
                    {modeReport.metrics?.false_accept_count ?? 0}
                    <span className="text-slate-500"> · FR </span>
                    {modeReport.metrics?.false_reject_count ?? 0}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="mt-3 rounded border border-slate-800/80 bg-slate-950/30 p-3 space-y-2">
            <div className="text-slate-200 text-xs">P2 Gold Corpus Scoring</div>
            <textarea
              value={p2GoldCasesText}
              onChange={(e) => setP2GoldCasesText(e.target.value)}
              className="h-40 w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-xs font-mono text-slate-200"
              placeholder="JSON array of gold corpus cases"
            />
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              <label className="text-[11px] text-slate-400">
                Min pass rate
                <Input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={p2PassCriteria.min_pass_rate}
                  onChange={(e) =>
                    setP2PassCriteria((prev) => ({
                      ...prev,
                      min_pass_rate: Math.min(1, Math.max(0, Number(e.target.value) || 0)),
                    }))
                  }
                  className="mt-1 h-8 border-slate-700 bg-slate-950 text-xs"
                />
              </label>
              <label className="text-[11px] text-slate-400">
                Max false accept rate
                <Input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={p2PassCriteria.max_false_accept_rate}
                  onChange={(e) =>
                    setP2PassCriteria((prev) => ({
                      ...prev,
                      max_false_accept_rate: Math.min(1, Math.max(0, Number(e.target.value) || 0)),
                    }))
                  }
                  className="mt-1 h-8 border-slate-700 bg-slate-950 text-xs"
                />
              </label>
              <label className="text-[11px] text-slate-400">
                Max false reject rate
                <Input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={p2PassCriteria.max_false_reject_rate}
                  onChange={(e) =>
                    setP2PassCriteria((prev) => ({
                      ...prev,
                      max_false_reject_rate: Math.min(1, Math.max(0, Number(e.target.value) || 0)),
                    }))
                  }
                  className="mt-1 h-8 border-slate-700 bg-slate-950 text-xs"
                />
              </label>
            </div>
            <Input
              value={p2GoldLabel}
              onChange={(e) => setP2GoldLabel(e.target.value)}
              className="h-8 border-slate-700 bg-slate-950 text-xs"
              placeholder="Report label"
            />
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                className="bg-blue-700 hover:bg-blue-800"
                disabled={isBusy || !p2GoldCasesText.trim()}
                onClick={() =>
                  void run(async () => {
                    const parsed = parseGoldCasesInput();
                    const report = await QcApi.evaluateGoldCorpus({ cases: parsed });
                    setP2GoldReport(report);
                    setStatus(
                      `Gold corpus scored · ${(report.pass_rate * 100).toFixed(1)}% pass · FA ${report.false_accept_count} · FR ${report.false_reject_count}`,
                    );
                  })
                }
              >
                Evaluate gold corpus
              </Button>
              <Button
                size="sm"
                className="bg-emerald-700 hover:bg-emerald-800"
                disabled={isBusy || !p2GoldReport || !p2GoldLabel.trim()}
                onClick={() =>
                  void run(async () => {
                    if (!p2GoldReport) return;
                    const saved = await QcApi.saveGoldCorpusReport({
                      label: p2GoldLabel.trim(),
                      report: p2GoldReport,
                      criteria: p2PassCriteria,
                    });
                    await loadGoldCorpusReports(10);
                    setStatus(
                      `Saved gold report ${saved.report_id.slice(0, 8)}... · criteria ${saved.pass_criteria_met ? 'PASS' : 'FAIL'}`,
                    );
                  })
                }
              >
                Save report
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="border-slate-700 bg-slate-900"
                disabled={isBusy}
                onClick={() =>
                  void run(async () => {
                    const count = await loadGoldCorpusReports(10);
                    setStatus(`Loaded ${count} saved gold reports`);
                  })
                }
              >
                Refresh saved reports
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="border-slate-700 bg-slate-900"
                disabled={!p2GoldReport}
                onClick={() =>
                  downloadJson(
                    `p2_gold_report_${Date.now()}.json`,
                    p2GoldReport,
                  )
                }
              >
                Download report JSON
              </Button>
            </div>
            {p2GoldReport ? (
              <div className="text-[11px] text-slate-300 space-y-1">
                <div>
                  <span className="text-slate-500">Pass rate:</span>{' '}
                  {(p2GoldReport.pass_rate * 100).toFixed(1)}% ({p2GoldReport.pass_cases}/
                  {p2GoldReport.total_cases})
                </div>
                <div>
                  <span className="text-slate-500">False accept:</span> {p2GoldReport.false_accept_count} (
                  {(p2GoldReport.false_accept_rate * 100).toFixed(1)}%)
                </div>
                <div>
                  <span className="text-slate-500">False reject:</span> {p2GoldReport.false_reject_count} (
                  {(p2GoldReport.false_reject_rate * 100).toFixed(1)}%)
                </div>
                <div>
                  <span className="text-slate-500">Pass criteria:</span>{' '}
                  <span
                    className={
                      p2GoldCriteriaPass == null
                        ? 'text-slate-300'
                        : p2GoldCriteriaPass
                          ? 'text-emerald-300'
                          : 'text-amber-300'
                    }
                  >
                    {p2GoldCriteriaPass == null ? 'n/a' : p2GoldCriteriaPass ? 'PASS' : 'FAIL'}
                  </span>
                </div>
              </div>
            ) : null}
            {p2GoldSavedReports.length ? (
              <div className="rounded border border-slate-800/80 bg-slate-950/20 p-2 text-[11px] text-slate-300">
                <div className="mb-1 text-slate-200">Saved benchmark reports</div>
                <div className="max-h-32 overflow-y-auto space-y-1 pr-1">
                  {p2GoldSavedReports.map((row) => (
                    <div key={row.report_id} className="rounded border border-slate-800/70 px-2 py-1">
                      <div>
                        <span className={row.pass_criteria_met ? 'text-emerald-300' : 'text-amber-300'}>
                          {row.pass_criteria_met ? 'PASS' : 'FAIL'}
                        </span>{' '}
                        · {row.label}
                      </div>
                      <div className="text-slate-500">
                        pass {(row.report.pass_rate * 100).toFixed(1)}% · FA{' '}
                        {(row.report.false_accept_rate * 100).toFixed(1)}% · FR{' '}
                        {(row.report.false_reject_rate * 100).toFixed(1)}%
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Card>
          </TabsContent>
        </Tabs>

        {(status || error || gpuBackend || latestRunFactoringSummary || latestReceipt) && (
          <Card className="bg-slate-900 border-slate-800 p-6">
            <div className="text-slate-100">Funding activity</div>
            {status ? <div className="mt-3 text-sm text-emerald-300">{status}</div> : null}
            {error ? <div className="mt-3 text-sm text-red-200">{error}</div> : null}
            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              <div className="rounded border border-slate-800/80 bg-slate-950/40 p-3 text-xs">
                <div className="text-slate-200 mb-2">GPU backend connectivity</div>
                {gpuBackend ? (
                  <>
                    <div className={gpuBackend.tcp_reachable ? 'text-emerald-300' : 'text-amber-300'}>
                      {gpuBackend.tcp_reachable ? 'Reachable' : 'Not reachable'} ·{' '}
                      <span className="font-mono">{gpuBackend.configured_base_url}</span>
                    </div>
                    <div className="mt-1 text-slate-400">
                      API POST target: <span className="font-mono">{gpuBackend.factor_post_url}</span>
                    </div>
                    {gpuBackend.factor_backend_kind ? (
                      <div className="mt-1 text-slate-400">
                        Backend kind: <span className="font-mono">{gpuBackend.factor_backend_kind}</span>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="text-slate-400">Backend status not loaded yet.</div>
                )}
                {gpuBackendError ? <div className="mt-1 text-red-200">{gpuBackendError}</div> : null}
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-3 border-slate-700 bg-slate-900"
                  disabled={gpuBackendBusy}
                  onClick={() => void loadGpuBackend()}
                >
                  {gpuBackendBusy ? 'Checking…' : 'Recheck GPU backend'}
                </Button>
              </div>

              <div className="rounded border border-slate-800/80 bg-slate-950/40 p-3 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-slate-200">Latest receipts for current job</div>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-slate-700 bg-slate-900"
                    disabled={isBusy || !jobId.trim()}
                    onClick={() =>
                      void run(async () => {
                        await refreshP1State(jobId.trim());
                        setStatus(`Loaded receipts for ${jobId.trim()}`);
                      })
                    }
                  >
                    Refresh receipts
                  </Button>
                </div>
                {!jobId.trim() ? (
                  <div className="mt-2 text-slate-500">Enter or create a Job ID to load receipts.</div>
                ) : latestReceipt ? (
                  <div className="mt-2 space-y-1 text-slate-300">
                    <div>
                      Event: <span className="font-mono text-slate-400">{latestReceipt.event_id.slice(0, 18)}...</span>
                    </div>
                    <div>
                      Position: <span className="font-mono text-slate-400">{latestReceipt.position_id}</span>
                    </div>
                    <div>
                      Delivered {latestReceipt.delivered_ngh.toFixed(2)} NGH · providers {latestReceipt.provider_count}
                    </div>
                    {latestReceipt.verification_hash ? (
                      <div className="font-mono text-[11px] text-slate-500 break-all">
                        verification {latestReceipt.verification_hash}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="mt-2 text-slate-500">No receipts yet for this job.</div>
                )}
              </div>
            </div>

            {latestRunFactoringSummary ? (
              <div className="mt-4">
                <FactoringSummaryReceipt
                  label="Latest factoring output from executed contract"
                  summary={latestRunFactoringSummary}
                />
              </div>
            ) : null}

            {latestReceiptProviderSummaries.length ? (
              <div className="mt-4 space-y-3">
                {latestReceiptProviderSummaries.map((summary, idx) => (
                  <FactoringSummaryReceipt
                    key={`receipt-summary-${idx}`}
                    label={`Receipt factoring output #${idx + 1}`}
                    summary={summary}
                  />
                ))}
              </div>
            ) : null}
          </Card>
        )}
        {lastDemoRun ? <ExecutionReceiptCard run={lastDemoRun} /> : null}
      </div>
    </div>
  );
}
