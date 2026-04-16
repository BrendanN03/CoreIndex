/** CoreIndex browser client. In dev, defaults to direct `http://127.0.0.1:<port>` (CORS-enabled) to avoid Vite `/coreindex-api` proxy hangs. Set `VITE_API_BASE_URL=/coreindex-api` to force the proxy. */

function formatApiErrorDetail(detail: unknown): string {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join('; ');
  }
  if (typeof detail === 'object') {
    return JSON.stringify(detail);
  }
  return String(detail);
}

function resolveApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (typeof raw === 'string') {
    const t = raw.trim();
    if (t !== '') {
      return t.replace(/\/+$/, '');
    }
  }
  if (import.meta.env.DEV) {
    const p = (import.meta.env.VITE_COREINDEX_API_PORT as string | undefined)?.trim() || '8010';
    return `http://127.0.0.1:${p}`;
  }
  return 'http://127.0.0.1:8010';
}

export const API_BASE_URL = resolveApiBaseUrl();

/** Typical API calls — fail fast if the server is down; long work uses explicit overrides. */
const REQUEST_TIMEOUT_MS = 45_000;
/** Status, listings, vouchers, positions — should answer in milliseconds when the API is up. */
const LIGHT_GET_TIMEOUT_MS = 25_000;
/** Login/register — snappy feedback. */
const AUTH_TIMEOUT_MS = 25_000;
/** GPU TCP probe + POST that only allocates a run id. */
const DEMO_GATEWAY_TIMEOUT_MS = 20_000;
/** Sync demo pipeline (remote CADO / factor). */
const DEMO_PROGRESS_TIMEOUT_MS = 720_000;
/** One progress poll (slim GET); allow slow JSON under heavy storage/sim load. */
const DEMO_RUN_POLL_TIMEOUT_MS = 120_000;

type RequestMethod = 'GET' | 'POST' | 'PUT' | 'DELETE';

function getStoredAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('coreindex_access_token');
}

function buildHeaders(token?: string, hasBody = false): HeadersInit {
  const headers: Record<string, string> = {};
  if (hasBody) {
    headers['Content-Type'] = 'application/json';
  }
  const resolvedToken = token ?? getStoredAccessToken();
  if (resolvedToken) {
    headers.Authorization = `Bearer ${resolvedToken}`;
  }
  return headers;
}

async function requestJson<TResponse>(
  path: string,
  options: {
    method?: RequestMethod;
    body?: unknown;
    token?: string | null;
    timeoutMs?: number;
  } = {},
): Promise<TResponse> {
  const method = options.method ?? 'GET';
  const hasBody = options.body !== undefined;
  const url = `${API_BASE_URL}${path}`;
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId =
    timeoutMs > 0
      ? globalThis.setTimeout(() => controller.abort(), timeoutMs)
      : null;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: buildHeaders(options.token ?? undefined, hasBody),
      body: hasBody ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error(
        `Request timed out after ${timeoutMs / 1000}s (${url}). ` +
          'The browser never got an HTTP response—usually the FastAPI process is down or Vite is proxying to the wrong port. ' +
          'Fix: run `npm run dev` from the **repo root** (it sets `VITE_API_PROXY_TARGET` for you) and use only that terminal’s Web URL, ' +
          'or set `VITE_API_PROXY_TARGET` in `apps/web/.env.local` to match the API port (try opening `http://127.0.0.1:<api-port>/` in the browser—it must return JSON).',
      );
    }
        if (e instanceof TypeError) {
      throw new Error(
        `Cannot reach the API at ${API_BASE_URL}. ` +
          'Start the API on port 8010 (repo root: `npm run dev` or `cd apps/api && uvicorn ...`). ' +
          'In dev the UI defaults to http://127.0.0.1:8010; set `VITE_API_BASE_URL=/coreindex-api` only if you rely on the Vite proxy.',
      );
    }
    throw e;
  } finally {
    if (timeoutId != null) globalThis.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const errorBody = (await response.json()) as { detail?: unknown };
      const formatted = formatApiErrorDetail(errorBody.detail);
      if (formatted) {
        message = formatted;
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }
  return (await response.json()) as TResponse;
}

async function requestForm<TResponse>(
  path: string,
  form: FormData,
  options: {
    method?: RequestMethod;
    token?: string | null;
    timeoutMs?: number;
  } = {},
): Promise<TResponse> {
  const method = options.method ?? 'POST';
  const url = `${API_BASE_URL}${path}`;
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId =
    timeoutMs > 0
      ? globalThis.setTimeout(() => controller.abort(), timeoutMs)
      : null;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: buildHeaders(options.token ?? undefined, false),
      body: form,
      signal: controller.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s (${url}).`);
    }
    if (e instanceof TypeError) {
      throw new Error(`Cannot reach the API at ${API_BASE_URL}.`);
    }
    throw e;
  } finally {
    if (timeoutId != null) globalThis.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const errorBody = (await response.json()) as { detail?: unknown };
      const formatted = formatApiErrorDetail(errorBody.detail);
      if (formatted) {
        message = formatted;
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  return (await response.json()) as TResponse;
}

function productKeyQuery(pk: ProductKeyDto): string {
  const p = new URLSearchParams();
  p.set('region', pk.region);
  p.set('iso_hour', String(pk.iso_hour));
  p.set('sla', pk.sla);
  p.set('tier', pk.tier);
  return p.toString();
}

function liveQuery(
  q: ProductKeyDto | ({ gpu_model: string } & Partial<ProductKeyDto> & { limit?: number }),
): string {
  const p = new URLSearchParams();
  if ('gpu_model' in q && q.gpu_model) {
    p.set('gpu_model', q.gpu_model);
  }
  if ('region' in q && q.region != null) p.set('region', q.region);
  if ('iso_hour' in q && q.iso_hour != null) p.set('iso_hour', String(q.iso_hour));
  if ('sla' in q && q.sla != null) p.set('sla', q.sla);
  if ('tier' in q && q.tier != null) p.set('tier', q.tier);
  if ('limit' in q && q.limit != null) p.set('limit', String(q.limit));
  return p.toString();
}

// ——— DTOs (frontend shapes; aligned with FastAPI JSON) ———

export type RegionDto = 'us-east' | 'us-west' | 'eu-central' | 'asia-pacific';
export type SlaDto = 'standard' | 'premium' | 'urgent';
export type TierDto = 'basic' | 'standard' | 'premium' | 'enterprise';

export type UserPublicDto = {
  user_id: string;
  email: string;
  display_name?: string | null;
  role: 'buyer' | 'seller';
  created_at: string;
};

export type TokenResponseDto = {
  access_token: string;
  token_type: string;
  expires_at?: string;
  user: UserPublicDto;
};

export type WindowDto = {
  region: RegionDto;
  iso_hour: number;
  sla: SlaDto;
  tier: TierDto;
};

export type ProductKeyDto = {
  region: RegionDto;
  iso_hour: number;
  sla: SlaDto;
  tier: TierDto;
};

export type PackageDescriptorDto = {
  package_id: string;
  size_estimate_ngh: number;
  first_output_estimate_seconds?: number;
  metadata?: Record<string, unknown>;
};

export type JobCreateRequestDto = {
  job_id: string;
  window: WindowDto;
  package_index: PackageDescriptorDto[];
};

export type JobResponseDto = {
  job_id: string;
  status: string;
  window: WindowDto;
  package_index: PackageDescriptorDto[];
  created_at?: string;
};

export type JobReceiptRowDto = {
  event_id: string;
  created_at: string;
  position_id: string;
  provider_count: number;
  delivered_ngh: number;
  settlement_status?: string | null;
  verification_hash?: string | null;
  blockchain_anchor?: Record<string, unknown> | null;
  payload: Record<string, unknown>;
};

export type JobReceiptsResponseDto = {
  job_id: string;
  receipt_count: number;
  receipts: JobReceiptRowDto[];
};

export type FeasibilityResponseDto = {
  ngh_required: number;
  earliest_start: string;
  voucher_gap: number;
  milestone_sanity: Record<string, boolean>;
};

export type NominationCreateRequestDto = WindowDto & {
  ngh_available: number;
  gpu_model: string;
  gpu_count: number;
};

export type NominationResponseDto = {
  nomination_id: string;
  region: RegionDto;
  iso_hour: number;
  sla: SlaDto;
  tier: TierDto;
  ngh_available: number;
  gpu_model: string;
  gpu_count: number;
  provider_id?: string | null;
  created_at: string;
};

export type LotDto = {
  lot_id: string;
  job_id?: string | null;
  status: string;
  window: WindowDto;
  created_at?: string;
};

export type MarketplaceGpuListingResponseDto = {
  listing_id: string;
  provider_id: string;
  gpu_model: string;
  gpu_count: number;
  region: RegionDto;
  iso_hour: number;
  sla: SlaDto;
  tier: TierDto;
  ngh_available: number;
  indicative_price_per_ngh: number;
  created_at: string;
};

export type PrepareReadyRequestDto = {
  device_ok: boolean;
  driver_ok: boolean;
  image_pulled: boolean;
  inputs_prefetched: boolean;
};

export type ResultRequestDto = {
  output_root: string;
  item_count: number;
  wall_time_seconds: number;
  raw_gpu_time_seconds?: number;
  logs_uri?: string;
};

export type MarketPositionResponseDto = {
  position_id: string;
  product_key: ProductKeyDto;
  side: string;
  quantity_ngh: number;
  price_per_ngh: number;
  notional: number;
  status: string;
  created_at: string;
  settled_at?: string | null;
  owner_id?: string | null;
};

export type VoucherBalanceResponseDto = {
  product_key: ProductKeyDto;
  balance_ngh: number;
  deposited_ngh: number;
};

export type VoucherDepositRequestDto = {
  job_id: string;
  product_key: ProductKeyDto;
  amount_ngh: number;
};

export type VoucherDepositResponseDto = {
  job_id: string;
  product_key: ProductKeyDto;
  deposited_ngh: number;
  remaining_balance_ngh: number;
};

export type ComputeDeliveryResponseDto = {
  position_id: string;
  job_id: string;
  delivered_ngh: number;
  remaining_wallet_ngh: number;
  factoring_summary: Record<string, unknown>;
  delivery_status: string;
};

export type ExecutionPreflightResponseDto = {
  position_id: string;
  job_id: string;
  ready_to_execute: boolean;
  reasons: string[];
  position_status: string;
  product_key_match: boolean;
  required_ngh: number;
  deposited_ngh: number;
  voucher_gap_ngh: number;
  milestone_sanity: {
    first_output_ok?: boolean;
    size_band_ok?: boolean;
  };
  matching_provider_count: number;
  total_available_gpus: number;
};

export type DemoBlockchainAnchorDto = {
  network_label: string;
  tx_hash: string;
  block_number?: number | null;
  explorer_url?: string | null;
};

export type DemoProviderExecutionResponseDto = {
  provider_id: string;
  gpu_count: number;
  factoring_summary: Record<string, unknown>;
  provider_reliability_score?: number | null;
  receipt_signature?: string | null;
  indicative_price_per_ngh?: number | null;
};

export type DemoRunResponseDto = {
  position_id: string;
  job_id: string;
  settlement_status: string;
  settlement_target_seconds: number;
  matched_gpu_count: number;
  matched_seller_count?: number;
  delivered_ngh: number;
  remaining_wallet_ngh: number;
  provider_executions: DemoProviderExecutionResponseDto[];
  provider_selection_policy: string;
  real_provider_only: boolean;
  synthetic_excluded: boolean;
  verification_passed: boolean;
  verification_hash: string;
  blockchain_anchor: DemoBlockchainAnchorDto;
  run_status: string;
  buyer_owner_id?: string | null;
  composite_to_factor?: string;
  futures_contract_notional?: number;
  futures_price_per_ngh?: number;
  futures_quantity_ngh?: number;
  consolidated_prime_factors?: number[];
  futures_product_key?: ProductKeyDto | null;
};

export type DemoRunProgressStepDto = {
  step_id: string;
  label: string;
  status: string;
  detail?: string | null;
  updated_at?: string | null;
};

export type DemoRunTrackResponseDto = {
  run_id: string;
  overall_status: string;
  steps: DemoRunProgressStepDto[];
  job_id?: string | null;
  position_id?: string | null;
  result?: DemoRunResponseDto | null;
  error?: string | null;
};

export type FullDemoRunRequestDto = {
  composite: string;
  region: RegionDto;
  iso_hour: number;
  sla: SlaDto;
  tier: TierDto;
  quantity_ngh: number;
  price_per_ngh: number;
  package_size_ngh: number;
  job_id?: string | null;
  gpu_model_label: string;
  target_settle_seconds: number;
};

export type FullDemoRunStartResponseDto = { run_id: string };

export type CollectiveSessionCreateRequestDto = {
  session_id: string;
  job_id: string;
  region: RegionDto;
  iso_hour: number;
  sla: SlaDto;
  tier: TierDto;
  world_size: number;
  membership: string[];
  net_profile?: string;
};

export type CollectiveSessionResponseDto = {
  session_id: string;
  job_id: string;
  product_key: ProductKeyDto;
  world_size: number;
  membership: string[];
  net_profile: string;
  state: 'declared' | 'finalized' | 'ready' | 'active' | 'expired' | 'degraded';
  ready_members: string[];
  ready_count: number;
  created_at: string;
  finalized_at?: string | null;
  activated_at?: string | null;
  expired_at?: string | null;
};

export type SettlementRunResponseDto = {
  settlement_id: string;
  job_id: string;
  state: 'pending' | 'ready' | 'settled' | 'failed';
  receipt_root: string;
  qc_root: string;
  anchor_hash?: string | null;
  blockchain_anchor?: DemoBlockchainAnchorDto | null;
  accepted_ngh: number;
  rejected_ngh: number;
  created_at: string;
  settled_at?: string | null;
};

export type SettlementOnchainVerifyResponseDto = {
  settlement_id: string;
  tx_hash?: string | null;
  chain_reachable: boolean;
  verified: boolean;
  reason?: string | null;
  block_number?: number | null;
};

export type QcSubmissionResponseDto = {
  event_id: string;
  event_type: string;
  job_id: string;
  package_id: string;
  recorded: boolean;
};

export type QcModeDto = 'bit_exact' | 'fp_tolerant';

export type QcHashResponseDto = {
  merkle_root: string;
  chunk_roots: string[];
  bytes: number;
  chunks: number;
  chunk_size: number;
};

export type QcCanonicalizeResponseDto = {
  schema_id: string;
  canonicalization_version: string;
  record_count: number;
  merkle_root: string;
  chunk_roots: string[];
  bytes: number;
  chunks: number;
  chunk_size: number;
};

export type QcCompareResponseDto = {
  equal: boolean;
  mode: QcModeDto;
  summary: {
    schema_id: string;
    record_count: number | null;
    rel_err_max: number;
    ulp_max: number;
    differences: number;
  };
};

export type QcAdversarialSuiteResultDto = {
  variant: string;
  equal: boolean;
  expected_equal: boolean;
  expectation_passed: boolean;
  summary: {
    schema_id?: string;
    record_count?: number | null;
    rel_err_max?: number;
    ulp_max?: number;
    differences?: number;
  };
};

export type QcAdversarialSuiteResponseDto = {
  schema_id: string;
  mode: QcModeDto;
  rel_tol: number;
  max_ulp: number;
  variant_mode: 'table' | 'vectors' | 'relations';
  base_record_count: number;
  metrics?: {
    total_variants: number;
    expected_true_count: number;
    expected_false_count: number;
    false_accept_count: number;
    false_reject_count: number;
    expectation_pass_rate: number;
  };
  results: QcAdversarialSuiteResultDto[];
};

export type QcAdversarialMatrixResponseDto = {
  schema_id: string;
  rel_tol: number;
  max_ulp: number;
  variant_mode: 'table' | 'vectors' | 'relations';
  modes: QcAdversarialSuiteResponseDto[];
};

export type QcGoldCorpusCaseDto = {
  case_id: string;
  schema_id: string;
  mode: QcModeDto;
  rel_tol?: number;
  max_ulp?: number;
  expected_equal: boolean;
  a_rows: Record<string, unknown>[];
  b_rows: Record<string, unknown>[];
};

export type QcGoldCorpusResultDto = {
  case_id: string;
  schema_id: string;
  mode: QcModeDto;
  expected_equal: boolean;
  equal: boolean;
  pass: boolean;
  summary: {
    schema_id?: string;
    record_count?: number | null;
    rel_err_max?: number;
    ulp_max?: number;
    differences?: number;
  };
};

export type QcGoldCorpusEvaluateResponseDto = {
  total_cases: number;
  pass_cases: number;
  pass_rate: number;
  false_accept_count: number;
  false_reject_count: number;
  false_accept_rate: number;
  false_reject_rate: number;
  results: QcGoldCorpusResultDto[];
};

export type QcGoldPassCriteriaDto = {
  min_pass_rate: number;
  max_false_accept_rate: number;
  max_false_reject_rate: number;
};

export type QcGoldCorpusSavedReportDto = {
  report_id: string;
  created_at: string;
  label: string;
  criteria: QcGoldPassCriteriaDto;
  report: QcGoldCorpusEvaluateResponseDto;
  pass_criteria_met: boolean;
};

export type QcGoldCorpusSaveReportResponseDto = {
  report_id: string;
  created_at: string;
  label: string;
  pass_criteria_met: boolean;
};

export type QcGoldCorpusListReportsResponseDto = {
  count: number;
  reports: QcGoldCorpusSavedReportDto[];
};

export type GpuBackendStatusDto = {
  configured_base_url: string;
  factor_post_url: string;
  ssh_host_label: string;
  tcp_reachable: boolean;
  tcp_error?: string | null;
  requests_installed: boolean;
  setup_hint: string;
};

export type PlatformEventDto = {
  event_id: string;
  event_type: string;
  created_at: string;
  entity_type: string;
  entity_id: string;
  payload?: Record<string, unknown>;
};

export type PlatformStatusResponseDto = {
  current_phase: string;
  current_focus: string;
  api_version: string;
  capabilities: string[];
  event_count: number;
  recent_events: PlatformEventDto[];
};

export type MarketSimulationStatusResponseDto = {
  running: boolean;
  synthetic_buyer_agents: number;
  synthetic_seller_agents: number;
  ticks_per_second: number;
  started_at?: string | null;
  total_ticks: number;
  total_synthetic_orders: number;
};

export type MarketLiveOverviewRowDto = {
  gpu_model: string;
  product_key: ProductKeyDto;
  last_price_per_ngh: number;
  best_bid_per_ngh?: number | null;
  best_ask_per_ngh?: number | null;
  spread_per_ngh?: number | null;
  traded_volume_ngh_5m: number;
  active_order_count: number;
};

export type MarketLiveOverviewResponseDto = {
  as_of: string;
  rows: MarketLiveOverviewRowDto[];
};

export type ExchangeOrderBookLevelDto = {
  price_per_ngh: number;
  quantity_ngh: number;
};

export type ExchangeOrderBookResponseDto = {
  product_key: ProductKeyDto;
  bids: ExchangeOrderBookLevelDto[];
  asks: ExchangeOrderBookLevelDto[];
  spread?: number | null;
  best_bid?: number | null;
  best_ask?: number | null;
};

export type ExchangeTradeResponseDto = {
  trade_id: string;
  product_key: ProductKeyDto;
  buy_order_id: string;
  sell_order_id: string;
  price_per_ngh: number;
  quantity_ngh: number;
  notional: number;
  created_at: string;
};

export type ExchangeOrderResponseDto = {
  order_id: string;
  product_key: ProductKeyDto;
  side: 'buy' | 'sell';
  price_per_ngh: number;
  quantity_ngh: number;
  remaining_ngh: number;
  time_in_force: 'gtc' | 'ioc' | 'fok';
  status: string;
  created_at: string;
  owner_id?: string | null;
  subaccount_id?: string | null;
  strategy_tag?: string | null;
};

export type RiskSummaryResponseDto = {
  owner_id: string;
  used_notional: number;
  max_notional_limit: number;
  remaining_notional: number;
  used_margin: number;
  max_margin_limit: number;
  remaining_margin: number;
};

export type PretradeCheckResponseDto = {
  approved: boolean;
  reasons: string[];
  estimated_notional: number;
  estimated_margin: number;
  account_scope: string;
  subaccount_scope?: string | null;
  risk_snapshot: RiskSummaryResponseDto;
};

export type PositionSideDto = 'buy' | 'sell';

export type OptionTypeDto = 'call' | 'put';
export type OptionOrderSideDto = 'buy' | 'sell';
export type OptionOrderStatusDto = string;
export type TimeInForceDto = 'gtc' | 'ioc' | 'fok';

export type OptionGreeksDto = {
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
  rho: number;
};

export type OptionQuoteResponseDto = {
  option_type: OptionTypeDto;
  premium_per_ngh: number;
  premium_notional: number;
  intrinsic_value_per_ngh: number;
  time_value_per_ngh: number;
  greeks: OptionGreeksDto;
};

export type OptionContractResponseDto = {
  contract_id: string;
  product_key: ProductKeyDto;
  side: PositionSideDto;
  option_type: OptionTypeDto;
  forward_price_per_ngh: number;
  strike_price_per_ngh: number;
  time_to_expiry_years: number;
  implied_volatility: number;
  risk_free_rate: number;
  quantity_ngh: number;
  status: string;
  premium_per_ngh: number;
  premium_notional: number;
  created_at: string;
};

export type OptionOrderResponseDto = {
  order_id: string;
  contract_id: string;
  product_key: ProductKeyDto;
  side: OptionOrderSideDto;
  limit_price_per_ngh: number;
  quantity_ngh: number;
  remaining_ngh: number;
  time_in_force: TimeInForceDto;
  status: OptionOrderStatusDto;
  created_at: string;
  owner_id?: string | null;
  subaccount_id?: string | null;
  strategy_tag?: string | null;
};

export type OptionTradeResponseDto = {
  trade_id: string;
  contract_id: string;
  product_key: ProductKeyDto;
  buy_order_id: string;
  sell_order_id: string;
  price_per_ngh: number;
  quantity_ngh: number;
  notional: number;
  created_at: string;
};

export type OptionOrderBookLevelDto = { price_per_ngh: number; quantity_ngh: number };

export type OptionOrderBookResponseDto = {
  contract_id: string;
  bids: OptionOrderBookLevelDto[];
  asks: OptionOrderBookLevelDto[];
};

export type MarginStressResponseDto = {
  price_shock_pct: number;
  option_vol_shock_pct: number;
  stressed_unrealized_pnl: number;
  stress_margin_ratio: number;
  margin_call_triggered: boolean;
};

export type LiquidationResponseDto = {
  cancelled_futures_orders: number;
  cancelled_option_orders: number;
  reason: string;
};

export type RiskProfileResponseDto = {
  owner_id: string;
  max_notional_limit: number;
  max_margin_limit: number;
  max_order_notional: number;
  kill_switch_enabled: boolean;
  updated_at: string;
};

export type KillSwitchUpdateResponseDto = {
  owner_id: string;
  kill_switch_enabled: boolean;
  reason: string;
  updated_at: string;
};

export type StrategyLimitResponseDto = {
  owner_id: string;
  strategy_tag: string;
  max_order_notional: number;
  kill_switch_enabled: boolean;
  updated_at: string;
};

export type TradingSubaccountRiskResponseDto = {
  owner_id: string;
  subaccount_id: string;
  max_order_notional: number;
  kill_switch_enabled: boolean;
  updated_at: string;
};

export type TradingHierarchyResponseDto = {
  owner_id: string;
  org_id: string;
  account_id: string;
  subaccounts: TradingSubaccountRiskResponseDto[];
  updated_at: string;
};

export type FuturesPositionRowDto = {
  product_key: ProductKeyDto;
  net_quantity_ngh: number;
  avg_entry_price: number;
  last_price: number;
  unrealized_pnl: number;
};

export type OptionPositionRowDto = {
  contract_id: string;
  product_key: ProductKeyDto;
  net_quantity_ngh: number;
  avg_entry_premium: number;
  last_premium: number;
  unrealized_pnl: number;
};

export type TraderPortfolioResponseDto = {
  owner_id: string;
  unrealized_pnl_total: number;
  open_futures_order_count: number;
  open_option_order_count: number;
  recent_futures_trade_count: number;
  recent_option_trade_count: number;
  futures_positions: FuturesPositionRowDto[];
  option_positions: OptionPositionRowDto[];
  updated_at: string;
};

export type TraderExecutionMetricsResponseDto = {
  owner_id: string;
  futures_orders_submitted: number;
  futures_fill_ratio: number;
  option_orders_submitted: number;
  option_fill_ratio: number;
  avg_adverse_slippage_bps: number;
  avg_time_to_first_fill_seconds: number;
  updated_at: string;
};

export type StrategyExecutionMetricsRowDto = {
  strategy_tag: string;
  futures_orders_submitted: number;
  option_orders_submitted: number;
  futures_fill_ratio: number;
  option_fill_ratio: number;
  avg_adverse_slippage_bps: number;
};

export type StrategyExecutionMetricsResponseDto = {
  owner_id: string;
  rows: StrategyExecutionMetricsRowDto[];
  updated_at: string;
};

export type ProviderSlaSummaryResponseDto = {
  owner_id: string;
  total_lots: number;
  pending_lots: number;
  ready_lots: number;
  completed_lots: number;
  failed_lots: number;
  success_rate: number;
  avg_prepare_seconds: number;
  avg_completion_seconds: number;
  updated_at: string;
};

export type ProviderExecutionMetricsResponseDto = {
  owner_id: string;
  lots_observed: number;
  on_time_prepare_ratio: number;
  on_time_completion_ratio: number;
  avg_wall_time_seconds: number;
  updated_at: string;
};

export type ProviderFleetOverviewResponseDto = {
  owner_id: string;
  nominated_ngh_total: number;
  lots_active: number;
  lots_completed: number;
  utilization_ratio: number;
  updated_at: string;
};

// ——— API namespaces ———

export const AuthApi = {
  async login(body: { email: string; password: string }): Promise<TokenResponseDto> {
    return requestJson<TokenResponseDto>('/auth/login', {
      method: 'POST',
      body,
      token: null,
      timeoutMs: AUTH_TIMEOUT_MS,
    });
  },
  async register(body: {
    email: string;
    password: string;
    display_name?: string;
    role: 'buyer' | 'seller';
  }): Promise<UserPublicDto> {
    return requestJson<UserPublicDto>('/auth/register', {
      method: 'POST',
      body,
      token: null,
      timeoutMs: AUTH_TIMEOUT_MS,
    });
  },
  async me(token: string): Promise<UserPublicDto> {
    return requestJson<UserPublicDto>('/auth/me', { token, timeoutMs: AUTH_TIMEOUT_MS });
  },
};

export const JobApi = {
  async createJob(body: JobCreateRequestDto): Promise<JobResponseDto> {
    return requestJson<JobResponseDto>('/jobs', { method: 'POST', body });
  },
  async listJobs(limit = 120): Promise<JobResponseDto[]> {
    const q = limit > 0 ? `?limit=${encodeURIComponent(String(limit))}` : '';
    return requestJson<JobResponseDto[]>(`/jobs${q}`, { timeoutMs: LIGHT_GET_TIMEOUT_MS });
  },
  async getFeasibility(jobId: string): Promise<FeasibilityResponseDto> {
    return requestJson<FeasibilityResponseDto>(`/jobs/${encodeURIComponent(jobId)}/feasibility`);
  },
  async getReceipts(jobId: string): Promise<JobReceiptsResponseDto> {
    return requestJson<JobReceiptsResponseDto>(`/jobs/${encodeURIComponent(jobId)}/receipts`, {
      timeoutMs: LIGHT_GET_TIMEOUT_MS,
    });
  },
};

export const ProviderApi = {
  async getListings(): Promise<MarketplaceGpuListingResponseDto[]> {
    return requestJson<MarketplaceGpuListingResponseDto[]>('/provider/listings', {
      timeoutMs: LIGHT_GET_TIMEOUT_MS,
    });
  },
  async listLots(): Promise<LotDto[]> {
    return requestJson<LotDto[]>('/lots');
  },
  async createNomination(body: NominationCreateRequestDto): Promise<NominationResponseDto> {
    return requestJson<NominationResponseDto>('/nominations', { method: 'POST', body });
  },
  async createLot(body: { window: WindowDto; job_id?: string | null }): Promise<LotDto> {
    return requestJson<LotDto>('/lots', { method: 'POST', body });
  },
  async prepareReady(lotId: string, body: PrepareReadyRequestDto): Promise<unknown> {
    return requestJson(`/lots/${encodeURIComponent(lotId)}/prepare_ready`, {
      method: 'POST',
      body,
    });
  },
  async submitResult(lotId: string, body: ResultRequestDto): Promise<unknown> {
    return requestJson(`/lots/${encodeURIComponent(lotId)}/result`, { method: 'POST', body });
  },
  async getSlaSummary(): Promise<ProviderSlaSummaryResponseDto> {
    return requestJson('/provider/sla');
  },
  async getExecutionMetrics(): Promise<ProviderExecutionMetricsResponseDto> {
    return requestJson('/provider/execution-metrics');
  },
  async getFleetOverview(): Promise<ProviderFleetOverviewResponseDto> {
    return requestJson('/provider/fleet');
  },
};

export const VoucherApi = {
  async listVouchers(): Promise<VoucherBalanceResponseDto[]> {
    return requestJson<VoucherBalanceResponseDto[]>('/vouchers', { timeoutMs: LIGHT_GET_TIMEOUT_MS });
  },
  async deposit(body: VoucherDepositRequestDto): Promise<VoucherDepositResponseDto> {
    return requestJson<VoucherDepositResponseDto>('/vouchers/deposit', { method: 'POST', body });
  },
};

export const PlatformApi = {
  async getStatus(): Promise<PlatformStatusResponseDto> {
    return requestJson<PlatformStatusResponseDto>('/platform/status', {
      timeoutMs: LIGHT_GET_TIMEOUT_MS,
    });
  },
  async getGpuBackend(): Promise<GpuBackendStatusDto> {
    return requestJson('/platform/gpu-backend', { timeoutMs: DEMO_GATEWAY_TIMEOUT_MS });
  },
};

export const MarketApi = {
  async executeContract(
    positionId: string,
    body: {
      job_id: string;
      composite: string;
      target_settle_seconds?: number;
      auto_settle_if_open?: boolean;
      deposit_ngh?: number;
    },
  ): Promise<DemoRunResponseDto> {
    return requestJson<DemoRunResponseDto>(
      `/market/positions/${encodeURIComponent(positionId)}/demo-run`,
      { method: 'POST', body, timeoutMs: DEMO_PROGRESS_TIMEOUT_MS },
    );
  },
  async listPositions(limit?: number): Promise<MarketPositionResponseDto[]> {
    const q = limit != null && limit > 0 ? `?limit=${encodeURIComponent(String(limit))}` : '';
    return requestJson<MarketPositionResponseDto[]>(`/market/positions${q}`, {
      timeoutMs: LIGHT_GET_TIMEOUT_MS,
    });
  },
  async createPosition(body: {
    product_key: ProductKeyDto;
    side: PositionSideDto;
    quantity_ngh: number;
    price_per_ngh: number;
  }): Promise<MarketPositionResponseDto> {
    return requestJson<MarketPositionResponseDto>('/market/positions', { method: 'POST', body });
  },
  async settlePosition(positionId: string): Promise<MarketPositionResponseDto> {
    return requestJson<MarketPositionResponseDto>(
      `/market/positions/${encodeURIComponent(positionId)}/settle`,
      { method: 'POST' },
    );
  },
  async deliverPosition(
    positionId: string,
    body: { job_id: string; gpu_count: number; composite: string; deposit_ngh?: number },
  ): Promise<ComputeDeliveryResponseDto> {
    return requestJson<ComputeDeliveryResponseDto>(
      `/market/positions/${encodeURIComponent(positionId)}/deliver`,
      { method: 'POST', body, timeoutMs: DEMO_PROGRESS_TIMEOUT_MS },
    );
  },
  async getExecutionPreflight(
    positionId: string,
    jobId: string,
  ): Promise<ExecutionPreflightResponseDto> {
    const q = new URLSearchParams({ job_id: jobId.trim() });
    return requestJson<ExecutionPreflightResponseDto>(
      `/market/positions/${encodeURIComponent(positionId)}/preflight?${q.toString()}`,
      { timeoutMs: LIGHT_GET_TIMEOUT_MS },
    );
  },
  async runDemo(
    positionId: string,
    body: {
      job_id: string;
      composite: string;
      target_settle_seconds?: number;
      auto_settle_if_open?: boolean;
      deposit_ngh?: number;
    },
  ): Promise<DemoRunResponseDto> {
    return this.executeContract(positionId, body);
  },
  async startFullDemo(body: FullDemoRunRequestDto): Promise<FullDemoRunStartResponseDto> {
    return requestJson<FullDemoRunStartResponseDto>('/market/demo/full-run', {
      method: 'POST',
      body,
      timeoutMs: DEMO_GATEWAY_TIMEOUT_MS,
    });
  },
  async getDemoRunProgress(
    runId: string,
    options?: { slim?: boolean },
  ): Promise<DemoRunTrackResponseDto> {
    const slim = options?.slim ? '?slim=1' : '';
    return requestJson<DemoRunTrackResponseDto>(
      `/market/demo/run/${encodeURIComponent(runId)}${slim}`,
      { timeoutMs: DEMO_RUN_POLL_TIMEOUT_MS },
    );
  },
  async getPortfolio(): Promise<TraderPortfolioResponseDto> {
    return requestJson('/market/portfolio');
  },
  async getExecutionMetrics(): Promise<TraderExecutionMetricsResponseDto> {
    return requestJson('/market/execution-metrics');
  },
  async getStrategyMetrics(): Promise<StrategyExecutionMetricsResponseDto> {
    return requestJson('/market/strategy-metrics');
  },
  async getLiveOverview(): Promise<MarketLiveOverviewResponseDto> {
    return requestJson('/market/live/overview');
  },
  async getLiveOrderBook(
    q: ProductKeyDto | { gpu_model: string },
  ): Promise<ExchangeOrderBookResponseDto> {
    return requestJson<ExchangeOrderBookResponseDto>(
      `/market/live/orderbook?${liveQuery(q as ProductKeyDto & { gpu_model?: string; limit?: number })}`,
    );
  },
  async getLiveTape(
    q: ProductKeyDto | ({ gpu_model: string } & { limit?: number }),
  ): Promise<ExchangeTradeResponseDto[]> {
    return requestJson<ExchangeTradeResponseDto[]>(
      `/market/live/tape?${liveQuery(q as ProductKeyDto & { gpu_model?: string; limit?: number })}`,
    );
  },
  async startSimulation(body: {
    synthetic_buyer_agents: number;
    synthetic_seller_agents: number;
    ticks_per_second: number;
  }): Promise<MarketSimulationStatusResponseDto> {
    return requestJson<MarketSimulationStatusResponseDto>('/market/sim/start', {
      method: 'POST',
      body,
    });
  },
  async stopSimulation(): Promise<MarketSimulationStatusResponseDto> {
    return requestJson<MarketSimulationStatusResponseDto>('/market/sim/stop', { method: 'POST' });
  },
  async getSimulationStatus(): Promise<MarketSimulationStatusResponseDto> {
    return requestJson<MarketSimulationStatusResponseDto>('/market/sim/status', {
      timeoutMs: LIGHT_GET_TIMEOUT_MS,
    });
  },
};

export const SessionApi = {
  async createSession(body: CollectiveSessionCreateRequestDto): Promise<CollectiveSessionResponseDto> {
    return requestJson<CollectiveSessionResponseDto>('/sessions', { method: 'POST', body });
  },
  async listSessions(jobId?: string): Promise<CollectiveSessionResponseDto[]> {
    const q = jobId ? `?job_id=${encodeURIComponent(jobId)}` : '';
    return requestJson<CollectiveSessionResponseDto[]>(`/sessions${q}`, {
      timeoutMs: LIGHT_GET_TIMEOUT_MS,
    });
  },
  async finalizeSession(sessionId: string): Promise<{ session_id: string; state: string; ready_count: number; world_size: number }> {
    return requestJson(`/sessions/${encodeURIComponent(sessionId)}/finalize`, { method: 'POST' });
  },
  async markReady(sessionId: string, memberId: string): Promise<CollectiveSessionResponseDto> {
    return requestJson<CollectiveSessionResponseDto>(
      `/sessions/${encodeURIComponent(sessionId)}/ready`,
      { method: 'POST', body: { member_id: memberId } },
    );
  },
};

export const SettlementApi = {
  async anchor(body: {
    job_id: string;
    receipt_root: string;
    qc_root: string;
    note?: string;
  }): Promise<SettlementRunResponseDto> {
    return requestJson<SettlementRunResponseDto>('/settlement/anchor', {
      method: 'POST',
      body,
    });
  },
  async pay(body: {
    job_id: string;
    settlement_id: string;
    accepted_ngh: number;
    rejected_ngh?: number;
  }): Promise<SettlementRunResponseDto> {
    return requestJson<SettlementRunResponseDto>('/settlement/pay', {
      method: 'POST',
      body,
    });
  },
  async verifyOnchain(settlementId: string): Promise<SettlementOnchainVerifyResponseDto> {
    return requestJson<SettlementOnchainVerifyResponseDto>(
      `/settlement/${encodeURIComponent(settlementId)}/verify_onchain`,
      { timeoutMs: LIGHT_GET_TIMEOUT_MS },
    );
  },
};

export const QcApi = {
  async submitDuplicate(body: {
    job_id: string;
    package_id: string;
    provider_id?: string;
    verdict: string;
    detail?: string;
    metrics?: Record<string, unknown>;
  }): Promise<QcSubmissionResponseDto> {
    return requestJson<QcSubmissionResponseDto>('/qc/duplicate', {
      method: 'POST',
      body,
    });
  },
  async submitSpot(body: {
    job_id: string;
    package_id: string;
    provider_id?: string;
    verdict: string;
    detail?: string;
    metrics?: Record<string, unknown>;
  }): Promise<QcSubmissionResponseDto> {
    return requestJson<QcSubmissionResponseDto>('/qc/spot', {
      method: 'POST',
      body,
    });
  },
  async hashCanonical(input: string): Promise<QcHashResponseDto> {
    const file = new File([input], 'canonical.jsonl', { type: 'application/json' });
    const form = new FormData();
    form.append('file', file);
    return requestForm<QcHashResponseDto>('/qc/hash', form, {
      timeoutMs: LIGHT_GET_TIMEOUT_MS,
    });
  },
  async canonicalize(input: {
    schema_id: string;
    body: string;
    input_format?: string;
  }): Promise<QcCanonicalizeResponseDto> {
    const file = new File([input.body], 'payload.jsonl', { type: 'application/json' });
    const form = new FormData();
    form.append('file', file);
    const q = new URLSearchParams();
    q.set('schema_id', input.schema_id);
    if (input.input_format?.trim()) {
      q.set('input_format', input.input_format.trim());
    }
    return requestForm<QcCanonicalizeResponseDto>(`/qc/canonicalize?${q.toString()}`, form);
  },
  async compare(input: {
    schema_id: string;
    mode: QcModeDto;
    a: string;
    b: string;
    rel_tol?: number;
    max_ulp?: number;
  }): Promise<QcCompareResponseDto> {
    const form = new FormData();
    form.append('a', new File([input.a], 'a.jsonl', { type: 'application/json' }));
    form.append('b', new File([input.b], 'b.jsonl', { type: 'application/json' }));
    const q = new URLSearchParams();
    q.set('schema_id', input.schema_id);
    q.set('mode', input.mode);
    if (input.rel_tol != null) q.set('rel_tol', String(input.rel_tol));
    if (input.max_ulp != null) q.set('max_ulp', String(input.max_ulp));
    return requestForm<QcCompareResponseDto>(`/qc/compare?${q.toString()}`, form);
  },
  async runAdversarialSuite(input: {
    schema_id: string;
    mode: QcModeDto;
    rel_tol?: number;
    max_ulp?: number;
    variant_mode?: 'table' | 'vectors' | 'relations';
    base_rows: Record<string, unknown>[];
  }): Promise<QcAdversarialSuiteResponseDto> {
    return requestJson<QcAdversarialSuiteResponseDto>('/qc/adversarial_suite', {
      method: 'POST',
      body: input,
    });
  },
  async runAdversarialMatrix(input: {
    schema_id: string;
    rel_tol?: number;
    max_ulp?: number;
    variant_mode?: 'table' | 'vectors' | 'relations';
    base_rows: Record<string, unknown>[];
  }): Promise<QcAdversarialMatrixResponseDto> {
    return requestJson<QcAdversarialMatrixResponseDto>('/qc/adversarial_matrix', {
      method: 'POST',
      body: input,
    });
  },
  async evaluateGoldCorpus(input: {
    cases: QcGoldCorpusCaseDto[];
  }): Promise<QcGoldCorpusEvaluateResponseDto> {
    return requestJson<QcGoldCorpusEvaluateResponseDto>('/qc/gold_corpus/evaluate', {
      method: 'POST',
      body: input,
    });
  },
  async saveGoldCorpusReport(input: {
    label: string;
    report: QcGoldCorpusEvaluateResponseDto;
    criteria: QcGoldPassCriteriaDto;
  }): Promise<QcGoldCorpusSaveReportResponseDto> {
    return requestJson<QcGoldCorpusSaveReportResponseDto>('/qc/gold_corpus/report', {
      method: 'POST',
      body: input,
    });
  },
  async listGoldCorpusReports(limit = 20): Promise<QcGoldCorpusListReportsResponseDto> {
    const q = new URLSearchParams();
    q.set('limit', String(limit));
    return requestJson<QcGoldCorpusListReportsResponseDto>(`/qc/gold_corpus/reports?${q.toString()}`);
  },
};

export const ExchangeApi = {
  async createOrder(body: {
    product_key: ProductKeyDto;
    side: 'buy' | 'sell';
    quantity_ngh: number;
    price_per_ngh: number;
    time_in_force: TimeInForceDto;
    subaccount_id?: string;
    strategy_tag?: string;
  }): Promise<ExchangeOrderResponseDto> {
    return requestJson<ExchangeOrderResponseDto>('/exchange/orders', { method: 'POST', body });
  },
  async pretrade(body: {
    product_key: ProductKeyDto;
    side: 'buy' | 'sell';
    quantity_ngh: number;
    price_per_ngh: number;
    time_in_force: TimeInForceDto;
    subaccount_id?: string;
    strategy_tag?: string;
  }): Promise<PretradeCheckResponseDto> {
    return requestJson<PretradeCheckResponseDto>('/exchange/pretrade', { method: 'POST', body });
  },
  async listOrders(productKey: ProductKeyDto): Promise<ExchangeOrderResponseDto[]> {
    return requestJson<ExchangeOrderResponseDto[]>(
      `/exchange/orders?${productKeyQuery(productKey)}`,
    );
  },
  async cancelOrder(orderId: string): Promise<ExchangeOrderResponseDto> {
    return requestJson<ExchangeOrderResponseDto>(`/exchange/orders/${encodeURIComponent(orderId)}`, {
      method: 'DELETE',
    });
  },
  async amendOrder(
    orderId: string,
    body: { price_per_ngh?: number; quantity_ngh?: number },
  ): Promise<ExchangeOrderResponseDto> {
    return requestJson<ExchangeOrderResponseDto>(
      `/exchange/orders/${encodeURIComponent(orderId)}`,
      { method: 'PUT', body },
    );
  },
};

export const OptionsApi = {
  async quote(body: {
    option_type: OptionTypeDto;
    forward_price_per_ngh: number;
    strike_price_per_ngh: number;
    time_to_expiry_years: number;
    implied_volatility: number;
    risk_free_rate: number;
    quantity_ngh: number;
  }): Promise<OptionQuoteResponseDto> {
    return requestJson<OptionQuoteResponseDto>('/options/quote', { method: 'POST', body });
  },
  async createContract(body: {
    product_key: ProductKeyDto;
    side: PositionSideDto;
    option_type: OptionTypeDto;
    forward_price_per_ngh: number;
    strike_price_per_ngh: number;
    time_to_expiry_years: number;
    implied_volatility: number;
    risk_free_rate: number;
    quantity_ngh: number;
  }): Promise<OptionContractResponseDto> {
    return requestJson<OptionContractResponseDto>('/options/contracts', { method: 'POST', body });
  },
  async listContracts(productKey: ProductKeyDto): Promise<OptionContractResponseDto[]> {
    return requestJson<OptionContractResponseDto[]>(
      `/options/contracts?${productKeyQuery(productKey)}`,
    );
  },
  async createOrder(body: {
    contract_id: string;
    side: OptionOrderSideDto;
    limit_price_per_ngh: number;
    quantity_ngh: number;
    time_in_force?: TimeInForceDto;
    subaccount_id?: string;
    strategy_tag?: string;
  }): Promise<OptionOrderResponseDto> {
    return requestJson<OptionOrderResponseDto>('/options/orders', { method: 'POST', body });
  },
  async pretrade(body: {
    contract_id: string;
    side: OptionOrderSideDto;
    limit_price_per_ngh: number;
    quantity_ngh: number;
    time_in_force?: TimeInForceDto;
    subaccount_id?: string;
    strategy_tag?: string;
  }): Promise<PretradeCheckResponseDto> {
    return requestJson<PretradeCheckResponseDto>('/options/pretrade', { method: 'POST', body });
  },
  async listOrders(contractId: string): Promise<OptionOrderResponseDto[]> {
    return requestJson<OptionOrderResponseDto[]>(
      `/options/orders?contract_id=${encodeURIComponent(contractId)}`,
    );
  },
  async cancelOrder(orderId: string): Promise<OptionOrderResponseDto> {
    return requestJson<OptionOrderResponseDto>(`/options/orders/${encodeURIComponent(orderId)}`, {
      method: 'DELETE',
    });
  },
  async amendOrder(
    orderId: string,
    body: { limit_price_per_ngh?: number; quantity_ngh?: number },
  ): Promise<OptionOrderResponseDto> {
    return requestJson<OptionOrderResponseDto>(
      `/options/orders/${encodeURIComponent(orderId)}`,
      { method: 'PUT', body },
    );
  },
  async getOrderBook(contractId: string): Promise<OptionOrderBookResponseDto> {
    return requestJson<OptionOrderBookResponseDto>(
      `/options/orderbook?contract_id=${encodeURIComponent(contractId)}`,
    );
  },
  async listTrades(contractId: string, limit = 20): Promise<OptionTradeResponseDto[]> {
    return requestJson<OptionTradeResponseDto[]>(
      `/options/trades?contract_id=${encodeURIComponent(contractId)}&limit=${limit}`,
    );
  },
  async getRisk(): Promise<RiskSummaryResponseDto> {
    return requestJson('/options/risk');
  },
  async getStress(
    priceShockPct = -0.15,
    optionVolShockPct = 0.25,
  ): Promise<MarginStressResponseDto> {
    return requestJson<MarginStressResponseDto>(
      `/options/risk/stress?price_shock_pct=${encodeURIComponent(String(priceShockPct))}&option_vol_shock_pct=${encodeURIComponent(String(optionVolShockPct))}`,
    );
  },
  async liquidate(reason: string): Promise<LiquidationResponseDto> {
    return requestJson<LiquidationResponseDto>(
      `/options/risk/liquidate?reason=${encodeURIComponent(reason)}`,
      { method: 'POST' },
    );
  },
  async getRiskProfile(): Promise<RiskProfileResponseDto> {
    return requestJson('/options/risk/profile');
  },
  async updateRiskProfile(body: {
    max_notional_limit: number;
    max_margin_limit: number;
    max_order_notional: number;
  }): Promise<RiskProfileResponseDto> {
    return requestJson<RiskProfileResponseDto>('/options/risk/profile', { method: 'PUT', body });
  },
  async setKillSwitch(enabled: boolean, reason: string): Promise<KillSwitchUpdateResponseDto> {
    return requestJson<KillSwitchUpdateResponseDto>(
      `/options/risk/kill-switch?enabled=${encodeURIComponent(String(enabled))}&reason=${encodeURIComponent(reason)}`,
      { method: 'POST' },
    );
  },
  async listStrategyLimits(): Promise<StrategyLimitResponseDto[]> {
    return requestJson('/options/risk/strategies');
  },
  async upsertStrategyLimit(body: {
    strategy_tag: string;
    max_order_notional: number;
    kill_switch_enabled: boolean;
  }): Promise<StrategyLimitResponseDto> {
    return requestJson<StrategyLimitResponseDto>('/options/risk/strategies', {
      method: 'PUT',
      body,
    });
  },
  async listSubaccountLimits(): Promise<TradingSubaccountRiskResponseDto[]> {
    return requestJson('/options/risk/subaccounts');
  },
  async upsertSubaccountLimit(body: {
    subaccount_id: string;
    max_order_notional: number;
    kill_switch_enabled: boolean;
  }): Promise<TradingSubaccountRiskResponseDto> {
    return requestJson<TradingSubaccountRiskResponseDto>('/options/risk/subaccounts', {
      method: 'PUT',
      body,
    });
  },
  async getTradingHierarchy(): Promise<TradingHierarchyResponseDto> {
    return requestJson('/options/risk/hierarchy');
  },
};
