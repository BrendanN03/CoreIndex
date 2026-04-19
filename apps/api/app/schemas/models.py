from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class Region(str, Enum):
    """Supported regions for compute jobs"""

    US_EAST = "us-east"
    US_WEST = "us-west"
    EU_CENTRAL = "eu-central"
    ASIA_PACIFIC = "asia-pacific"


class SLA(str, Enum):
    """Service Level Agreement tiers"""

    STANDARD = "standard"
    PREMIUM = "premium"
    URGENT = "urgent"


class Tier(str, Enum):
    """Compute tier levels"""

    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class Window(BaseModel):
    """Window specification for job execution"""

    region: Region
    iso_hour: int = Field(..., ge=0, le=23, description="ISO hour (0-23)")
    sla: SLA
    tier: Tier


class ProductKey(BaseModel):
    """Canonical market key shared by positions, vouchers, and jobs."""

    region: Region
    iso_hour: int = Field(..., ge=0, le=23, description="ISO hour (0-23)")
    sla: SLA
    tier: Tier

    @classmethod
    def from_window(cls, window: "Window") -> "ProductKey":
        return cls(
            region=window.region,
            iso_hour=window.iso_hour,
            sla=window.sla,
            tier=window.tier,
        )

    def as_storage_key(self) -> str:
        return f"{self.region.value}:{self.iso_hour}:{self.sla.value}:{self.tier.value}"


class PackageDescriptor(BaseModel):
    """Descriptor for a compute package"""

    package_id: str = Field(..., description="Unique identifier for the package")
    size_estimate_ngh: float = Field(
        ..., gt=0, description="Estimated size in NGH (Network GPU Hours)"
    )
    first_output_estimate_seconds: Optional[int] = Field(
        None, description="Estimated time to first output in seconds"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional package metadata"
    )


class JobCreateRequest(BaseModel):
    """Request model for creating a new job"""

    job_id: str = Field(..., description="Unique identifier for the job")
    window: Window
    package_index: List[PackageDescriptor] = Field(
        ..., min_length=1, description="List of package descriptors"
    )


class JobStatus(str, Enum):
    """Job status enumeration"""

    PENDING = "pending"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class VoucherState(str, Enum):
    """Lifecycle state for physically delivered compute claims."""

    MINTED = "minted"
    DEPOSITED = "deposited"
    CONSUMED = "consumed"


class SessionState(str, Enum):
    """Lifecycle state for collective sessions."""

    DECLARED = "declared"
    FINALIZED = "finalized"
    READY = "ready"
    ACTIVE = "active"
    EXPIRED = "expired"
    DEGRADED = "degraded"


class SettlementState(str, Enum):
    """Lifecycle state for settlement runs."""

    PENDING = "pending"
    READY = "ready"
    SETTLED = "settled"
    FAILED = "failed"


class CollectiveSessionCreateRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=96)
    job_id: str = Field(..., min_length=1, max_length=96)
    region: Region
    iso_hour: int = Field(..., ge=0, le=23)
    sla: SLA
    tier: Tier
    world_size: int = Field(..., ge=1, le=512)
    membership: List[str] = Field(..., min_length=1)
    net_profile: str = Field("collective_v1", min_length=1, max_length=64)


class CollectiveSessionResponse(BaseModel):
    session_id: str
    job_id: str
    product_key: ProductKey
    world_size: int
    membership: List[str]
    net_profile: str
    state: SessionState
    ready_members: List[str] = Field(default_factory=list)
    ready_count: int = Field(0, ge=0)
    created_at: str
    finalized_at: Optional[str] = None
    activated_at: Optional[str] = None
    expired_at: Optional[str] = None


class SessionReadyRequest(BaseModel):
    member_id: str = Field(..., min_length=1, max_length=128)


class SessionFinalizeResponse(BaseModel):
    session_id: str
    state: SessionState
    ready_count: int = Field(..., ge=0)
    world_size: int = Field(..., ge=1)


class JobReceiptRow(BaseModel):
    event_id: str
    created_at: str
    position_id: str
    provider_count: int = Field(0, ge=0)
    delivered_ngh: float = Field(0.0, ge=0)
    settlement_status: Optional[str] = None
    verification_hash: Optional[str] = None
    blockchain_anchor: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class JobReceiptsResponse(BaseModel):
    job_id: str
    receipt_count: int = Field(0, ge=0)
    receipts: List[JobReceiptRow] = Field(default_factory=list)


class SettlementAnchorRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    receipt_root: str = Field(..., min_length=8)
    qc_root: str = Field(..., min_length=8)
    note: Optional[str] = Field(None, max_length=280)


class SettlementPayRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    settlement_id: str = Field(..., min_length=1)
    accepted_ngh: float = Field(..., ge=0)
    rejected_ngh: float = Field(0.0, ge=0)


class SettlementRunResponse(BaseModel):
    settlement_id: str
    job_id: str
    state: SettlementState
    receipt_root: str
    qc_root: str
    anchor_hash: Optional[str] = None
    blockchain_anchor: Optional[Dict[str, Any]] = None
    accepted_ngh: float = Field(0.0, ge=0)
    rejected_ngh: float = Field(0.0, ge=0)
    created_at: str
    settled_at: Optional[str] = None


class SettlementOnchainVerifyResponse(BaseModel):
    settlement_id: str
    tx_hash: Optional[str] = None
    chain_reachable: bool
    verified: bool
    reason: Optional[str] = None
    block_number: Optional[int] = None


class PlatformEvent(BaseModel):
    """Minimal event shape used for audit-friendly demo state."""

    event_id: str
    event_type: str
    created_at: str
    entity_type: str
    entity_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class VoucherLedgerOp(BaseModel):
    """Single simulated multi-token ledger step (ERC-1155 style narrative over platform events)."""

    op_kind: str
    title: str
    detail: str
    event_type: str
    event_id: str
    created_at: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VoucherChainBlock(BaseModel):
    """One logical block keyed off an accepted compute delivery (same job/position as the main UI)."""

    block_index: int
    chain_height: int
    prev_block_hash: Optional[str] = None
    block_hash: str
    appended_at: str
    job_id: str
    position_id: str
    delivery_event_id: str
    delivery_created_at: str
    delivered_ngh: Optional[float] = None
    verification_hash: Optional[str] = None
    verification_passed: Optional[bool] = None
    blockchain_anchor: Optional[Dict[str, Any]] = None
    demo_mode: Optional[str] = None
    related_ops: List[VoucherLedgerOp] = Field(default_factory=list)
    delivery_op: VoucherLedgerOp


class VoucherChainLedgerResponse(BaseModel):
    """Voucher escrow + settlement anchors + delivery commits as an append-only chain."""

    generated_at: str
    event_window: int
    chain_length: int = 0
    chain_head_hash: Optional[str] = None
    blocks: List[VoucherChainBlock] = Field(default_factory=list)

# Backward-compatible aliases while older imports are migrated.
JudgeLedgerOp = VoucherLedgerOp
JudgeChainBlock = VoucherChainBlock
JudgeChainLedgerResponse = VoucherChainLedgerResponse


class PlatformStatusResponse(BaseModel):
    """Visible platform metadata exposed to the frontend shell."""

    current_phase: str
    current_focus: str
    api_version: str
    capabilities: List[str]
    event_count: int = Field(..., ge=0)
    recent_events: List[PlatformEvent] = Field(default_factory=list)


class GpuBackendStatusResponse(BaseModel):
    """Connectivity hints for the remote CADO / GPU HTTP service (demo factoring step)."""

    configured_base_url: str
    factor_post_url: str
    ssh_host_label: str
    tcp_reachable: bool
    tcp_error: Optional[str] = None
    requests_installed: bool = True
    setup_hint: str
    # When reachable, optional probe of GET {base}/ — dev stub reports service name + trial limit.
    factor_backend_kind: Optional[str] = None
    dev_stub_max_composite_digits: Optional[int] = None


class PositionSide(str, Enum):
    """Trade side for exchange positions."""

    BUY = "buy"
    SELL = "sell"


class OptionType(str, Enum):
    """Supported option styles for compute contracts."""

    CALL = "call"
    PUT = "put"


class OptionContractStatus(str, Enum):
    """Lifecycle state for listed option contracts."""

    OPEN = "open"
    EXPIRED = "expired"


class OptionOrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OptionOrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class MarketPositionStatus(str, Enum):
    """Lifecycle state for physically deliverable market positions."""

    OPEN = "open"
    SETTLED = "settled"


class MarketPositionCreateRequest(BaseModel):
    """Request to create a demo physically deliverable compute position."""

    product_key: ProductKey
    side: PositionSide = PositionSide.BUY
    quantity_ngh: float = Field(..., gt=0)
    price_per_ngh: float = Field(..., gt=0)
    close_in_seconds: int = Field(
        default=300,
        ge=0,
        le=31_622_400,
        description="Seconds from creation until the futures contract closes (0 = already closed).",
    )

    @field_validator("close_in_seconds", mode="before")
    @classmethod
    def _coerce_close_in_seconds(cls, value: object) -> object:
        """JSON may send floats; coerce so the horizon is never dropped to the default by validation noise."""
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return value


class MarketPositionResponse(BaseModel):
    """Exchange position summary shown in the buyer UI."""

    position_id: str
    product_key: ProductKey
    side: PositionSide
    quantity_ngh: float
    price_per_ngh: float
    notional: float
    status: MarketPositionStatus
    created_at: str
    closes_at: Optional[str] = None
    close_in_seconds: Optional[int] = Field(
        default=None,
        ge=0,
        le=31_622_400,
        description="Echo of requested close horizon at creation; used if closes_at is absent or unparsable.",
    )
    seconds_until_close: Optional[int] = Field(
        default=None,
        ge=0,
        description="Seconds remaining until close; recomputed on each list/create response (not persisted).",
    )
    settled_at: Optional[str] = None
    owner_id: Optional[str] = None


class VoucherBalanceResponse(BaseModel):
    """Wallet-like voucher balance for one product key."""

    product_key: ProductKey
    balance_ngh: float = Field(..., ge=0)
    deposited_ngh: float = Field(..., ge=0)


class VoucherDepositRequest(BaseModel):
    """Escrow vouchers to a job for a given product key."""

    job_id: str
    product_key: ProductKey
    amount_ngh: float = Field(..., gt=0)


class VoucherDepositResponse(BaseModel):
    """Result of escrowing vouchers against a job."""

    job_id: str
    product_key: ProductKey
    deposited_ngh: float = Field(..., ge=0)
    remaining_balance_ngh: float = Field(..., ge=0)


class ExchangeOrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ExchangeOrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


class ExchangeOrderCreateRequest(BaseModel):
    product_key: ProductKey
    side: ExchangeOrderSide
    price_per_ngh: float = Field(..., gt=0)
    quantity_ngh: float = Field(..., gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    subaccount_id: Optional[str] = None
    strategy_tag: Optional[str] = None


class ExchangeOrderAmendRequest(BaseModel):
    price_per_ngh: Optional[float] = Field(None, gt=0)
    quantity_ngh: Optional[float] = Field(None, gt=0)


class ExchangeOrderResponse(BaseModel):
    order_id: str
    product_key: ProductKey
    side: ExchangeOrderSide
    price_per_ngh: float
    quantity_ngh: float
    remaining_ngh: float
    time_in_force: TimeInForce = TimeInForce.GTC
    status: ExchangeOrderStatus
    created_at: str
    owner_id: Optional[str] = None
    subaccount_id: Optional[str] = None
    strategy_tag: Optional[str] = None


class ExchangeTradeResponse(BaseModel):
    trade_id: str
    product_key: ProductKey
    buy_order_id: str
    sell_order_id: str
    price_per_ngh: float
    quantity_ngh: float
    notional: float
    created_at: str


class ExchangeOrderBookLevel(BaseModel):
    price_per_ngh: float
    quantity_ngh: float


class ExchangeOrderBookResponse(BaseModel):
    product_key: ProductKey
    bids: List[ExchangeOrderBookLevel]
    asks: List[ExchangeOrderBookLevel]
    spread: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None


class OptionQuoteRequest(BaseModel):
    option_type: OptionType
    forward_price_per_ngh: float = Field(..., gt=0)
    strike_price_per_ngh: float = Field(..., gt=0)
    time_to_expiry_years: float = Field(..., gt=0)
    implied_volatility: float = Field(..., gt=0)
    risk_free_rate: float = Field(0.0)
    quantity_ngh: float = Field(1.0, gt=0)


class OptionGreeks(BaseModel):
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


class OptionQuoteResponse(BaseModel):
    option_type: OptionType
    premium_per_ngh: float = Field(..., ge=0)
    premium_notional: float = Field(..., ge=0)
    intrinsic_value_per_ngh: float = Field(..., ge=0)
    time_value_per_ngh: float = Field(..., ge=0)
    greeks: OptionGreeks


class OptionContractCreateRequest(BaseModel):
    product_key: ProductKey
    side: PositionSide = PositionSide.BUY
    option_type: OptionType
    forward_price_per_ngh: float = Field(..., gt=0)
    strike_price_per_ngh: float = Field(..., gt=0)
    time_to_expiry_years: float = Field(..., gt=0)
    implied_volatility: float = Field(..., gt=0)
    risk_free_rate: float = Field(0.0)
    quantity_ngh: float = Field(..., gt=0)


class OptionContractResponse(BaseModel):
    contract_id: str
    product_key: ProductKey
    side: PositionSide
    option_type: OptionType
    forward_price_per_ngh: float
    strike_price_per_ngh: float
    time_to_expiry_years: float
    implied_volatility: float
    risk_free_rate: float
    quantity_ngh: float
    status: OptionContractStatus
    premium_per_ngh: float
    premium_notional: float
    created_at: str
    owner_id: Optional[str] = None


class OptionOrderCreateRequest(BaseModel):
    contract_id: str
    side: OptionOrderSide
    limit_price_per_ngh: float = Field(..., gt=0)
    quantity_ngh: float = Field(..., gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    subaccount_id: Optional[str] = None
    strategy_tag: Optional[str] = None


class OptionOrderAmendRequest(BaseModel):
    limit_price_per_ngh: Optional[float] = Field(None, gt=0)
    quantity_ngh: Optional[float] = Field(None, gt=0)


class OptionOrderResponse(BaseModel):
    order_id: str
    contract_id: str
    product_key: ProductKey
    side: OptionOrderSide
    limit_price_per_ngh: float
    quantity_ngh: float
    remaining_ngh: float
    time_in_force: TimeInForce = TimeInForce.GTC
    status: OptionOrderStatus
    created_at: str
    owner_id: Optional[str] = None
    subaccount_id: Optional[str] = None
    strategy_tag: Optional[str] = None


class OptionTradeResponse(BaseModel):
    trade_id: str
    contract_id: str
    product_key: ProductKey
    buy_order_id: str
    sell_order_id: str
    price_per_ngh: float
    quantity_ngh: float
    notional: float
    created_at: str


class OptionOrderBookLevel(BaseModel):
    price_per_ngh: float
    quantity_ngh: float


class OptionOrderBookResponse(BaseModel):
    contract_id: str
    product_key: ProductKey
    bids: List[OptionOrderBookLevel]
    asks: List[OptionOrderBookLevel]
    spread: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None


class RiskSummaryResponse(BaseModel):
    owner_id: str
    max_notional_limit: float = Field(..., ge=0)
    used_notional: float = Field(..., ge=0)
    remaining_notional: float = Field(..., ge=0)
    max_margin_limit: float = Field(..., ge=0)
    used_margin: float = Field(..., ge=0)
    remaining_margin: float = Field(..., ge=0)
    updated_at: str


class FuturesPositionRow(BaseModel):
    product_key: ProductKey
    net_quantity_ngh: float
    avg_entry_price: float
    last_price: float
    unrealized_pnl: float


class OptionPositionRow(BaseModel):
    contract_id: str
    product_key: ProductKey
    net_quantity_ngh: float
    avg_entry_premium: float
    last_premium: float
    unrealized_pnl: float


class TraderPortfolioResponse(BaseModel):
    owner_id: str
    unrealized_pnl_total: float
    open_futures_order_count: int = Field(..., ge=0)
    open_option_order_count: int = Field(..., ge=0)
    recent_futures_trade_count: int = Field(..., ge=0)
    recent_option_trade_count: int = Field(..., ge=0)
    futures_positions: List[FuturesPositionRow]
    option_positions: List[OptionPositionRow]
    updated_at: str


class MarginStressResponse(BaseModel):
    owner_id: str
    base_unrealized_pnl: float
    stressed_unrealized_pnl: float
    used_margin: float = Field(..., ge=0)
    stress_margin_ratio: float = Field(..., ge=0)
    margin_call_triggered: bool
    price_shock_pct: float
    option_vol_shock_pct: float
    updated_at: str


class LiquidationResponse(BaseModel):
    owner_id: str
    cancelled_futures_orders: int = Field(..., ge=0)
    cancelled_option_orders: int = Field(..., ge=0)
    liquidation_triggered: bool
    reason: str
    updated_at: str


class RiskProfileResponse(BaseModel):
    owner_id: str
    max_notional_limit: float = Field(..., gt=0)
    max_margin_limit: float = Field(..., gt=0)
    max_order_notional: float = Field(..., gt=0)
    kill_switch_enabled: bool
    updated_at: str


class RiskProfileUpdateRequest(BaseModel):
    max_notional_limit: Optional[float] = Field(None, gt=0)
    max_margin_limit: Optional[float] = Field(None, gt=0)
    max_order_notional: Optional[float] = Field(None, gt=0)


class KillSwitchUpdateResponse(BaseModel):
    owner_id: str
    kill_switch_enabled: bool
    reason: str
    updated_at: str


class ProviderSlaSummaryResponse(BaseModel):
    owner_id: str
    total_lots: int = Field(..., ge=0)
    pending_lots: int = Field(..., ge=0)
    ready_lots: int = Field(..., ge=0)
    completed_lots: int = Field(..., ge=0)
    failed_lots: int = Field(..., ge=0)
    success_rate: float = Field(..., ge=0)
    avg_prepare_seconds: float = Field(..., ge=0)
    avg_completion_seconds: float = Field(..., ge=0)
    updated_at: str


class TraderExecutionMetricsResponse(BaseModel):
    owner_id: str
    futures_orders_submitted: int = Field(..., ge=0)
    futures_fill_ratio: float = Field(..., ge=0)
    option_orders_submitted: int = Field(..., ge=0)
    option_fill_ratio: float = Field(..., ge=0)
    avg_adverse_slippage_bps: float = Field(..., ge=0)
    avg_time_to_first_fill_seconds: float = Field(..., ge=0)
    updated_at: str


class StrategyLimitResponse(BaseModel):
    owner_id: str
    strategy_tag: str
    max_order_notional: float = Field(..., gt=0)
    kill_switch_enabled: bool
    updated_at: str


class StrategyLimitUpdateRequest(BaseModel):
    strategy_tag: str = Field(..., min_length=1, max_length=64)
    max_order_notional: float = Field(..., gt=0)
    kill_switch_enabled: bool = False


class StrategyExecutionMetricsRow(BaseModel):
    strategy_tag: str
    futures_orders_submitted: int = Field(..., ge=0)
    option_orders_submitted: int = Field(..., ge=0)
    futures_fill_ratio: float = Field(..., ge=0)
    option_fill_ratio: float = Field(..., ge=0)
    avg_adverse_slippage_bps: float = Field(..., ge=0)


class StrategyExecutionMetricsResponse(BaseModel):
    owner_id: str
    rows: List[StrategyExecutionMetricsRow]
    updated_at: str


class ProviderExecutionMetricsResponse(BaseModel):
    owner_id: str
    lots_observed: int = Field(..., ge=0)
    on_time_prepare_ratio: float = Field(..., ge=0)
    on_time_completion_ratio: float = Field(..., ge=0)
    avg_wall_time_seconds: float = Field(..., ge=0)
    updated_at: str


class ProviderFleetOverviewResponse(BaseModel):
    owner_id: str
    nominated_ngh_total: float = Field(..., ge=0)
    lots_active: int = Field(..., ge=0)
    lots_completed: int = Field(..., ge=0)
    utilization_ratio: float = Field(..., ge=0)
    updated_at: str


class ExchangePretradeRequest(BaseModel):
    product_key: ProductKey
    side: ExchangeOrderSide
    price_per_ngh: float = Field(..., gt=0)
    quantity_ngh: float = Field(..., gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    subaccount_id: Optional[str] = None
    strategy_tag: Optional[str] = None


class OptionPretradeRequest(BaseModel):
    contract_id: str
    side: OptionOrderSide
    limit_price_per_ngh: float = Field(..., gt=0)
    quantity_ngh: float = Field(..., gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    subaccount_id: Optional[str] = None
    strategy_tag: Optional[str] = None


class PretradeCheckResponse(BaseModel):
    approved: bool
    reasons: List[str]
    estimated_notional: float = Field(..., ge=0)
    estimated_margin: float = Field(..., ge=0)
    account_scope: str
    subaccount_scope: Optional[str] = None
    risk_snapshot: RiskSummaryResponse


class ComputeDeliveryRequest(BaseModel):
    job_id: str
    gpu_count: int = Field(..., ge=1, le=4)
    composite: str = Field(..., min_length=2)
    deposit_ngh: Optional[float] = Field(None, gt=0)


class ComputeDeliveryResponse(BaseModel):
    position_id: str
    job_id: str
    delivered_ngh: float = Field(..., ge=0)
    remaining_wallet_ngh: float = Field(..., ge=0)
    factoring_summary: Dict[str, Any]
    delivery_status: str


class ExecutionPreflightResponse(BaseModel):
    position_id: str
    job_id: str
    ready_to_execute: bool
    reasons: List[str] = Field(default_factory=list)
    position_status: str
    contract_closed: bool
    closes_at: Optional[str] = None
    seconds_until_close: int = Field(..., ge=0)
    product_key_match: bool
    required_ngh: float = Field(..., ge=0)
    deposited_ngh: float = Field(..., ge=0)
    voucher_gap_ngh: float = Field(..., ge=0)
    milestone_sanity: Dict[str, bool] = Field(default_factory=dict)
    matching_provider_count: int = Field(0, ge=0)
    total_available_gpus: int = Field(0, ge=0)


class ProviderSplitRequest(BaseModel):
    provider_id: str = Field(..., min_length=1, max_length=64)
    gpu_count: int = Field(..., ge=1, le=4)


class DemoBlockchainAnchorResponse(BaseModel):
    network_label: str
    tx_hash: str
    block_number: Optional[int] = None
    explorer_url: Optional[str] = None


class DemoProviderExecutionResponse(BaseModel):
    provider_id: str
    gpu_count: int
    factoring_summary: Dict[str, Any]
    provider_reliability_score: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description="Observed provider reliability score used during matching",
    )
    receipt_signature: Optional[str] = Field(
        None,
        description="HMAC signature over provider execution payload for attestation",
    )
    indicative_price_per_ngh: Optional[float] = Field(
        None,
        description="Listing anchor price for this seller at match time (NGH notional / NGH)",
    )


class DemoRunRequest(BaseModel):
    job_id: str
    composite: str = Field(..., min_length=2)
    deposit_ngh: Optional[float] = Field(None, gt=0)
    auto_settle_if_open: bool = True
    target_settle_seconds: int = Field(
        300,
        ge=30,
        le=31_622_400,
        description="Futures settlement / delivery horizon (30s–366d)",
    )


class DemoRunResponse(BaseModel):
    position_id: str
    job_id: str
    settlement_status: str
    settlement_target_seconds: int
    matched_gpu_count: int = Field(..., ge=1, le=4)
    matched_seller_count: int = Field(
        0,
        ge=0,
        le=4,
        description="Distinct providers allocated (max 4); GPU count sums to matched_gpu_count",
    )
    delivered_ngh: float = Field(..., ge=0)
    remaining_wallet_ngh: float = Field(..., ge=0)
    provider_executions: List[DemoProviderExecutionResponse]
    provider_selection_policy: str = "best_price_capacity_real_only"
    real_provider_only: bool = True
    synthetic_excluded: bool = True
    verification_passed: bool
    verification_hash: str
    blockchain_anchor: DemoBlockchainAnchorResponse
    run_status: str
    buyer_owner_id: Optional[str] = None
    composite_to_factor: str = ""
    futures_contract_notional: float = Field(0.0, ge=0)
    futures_price_per_ngh: float = Field(0.0, ge=0)
    futures_quantity_ngh: float = Field(0.0, ge=0)
    execution_market_price_per_ngh: Optional[float] = Field(
        None,
        ge=0,
        description="Market-derived execution clearing price from matched seller liquidity",
    )
    execution_market_notional: Optional[float] = Field(
        None,
        ge=0,
        description="Execution NGH multiplied by the market-derived clearing price",
    )
    consolidated_prime_factors: List[int] = Field(
        default_factory=list,
        description="Prime factors reported across all GPU runs (order preserved per provider)",
    )
    futures_product_key: Optional[Dict[str, Any]] = Field(
        None,
        description="Region / hour / SLA / tier for the underlying futures leg",
    )


class DemoProgressStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class DemoRunProgressStep(BaseModel):
    step_id: str
    label: str
    status: DemoProgressStepStatus
    detail: Optional[str] = None
    updated_at: Optional[str] = None


class DemoRunTrackResponse(BaseModel):
    run_id: str
    overall_status: str
    steps: List[DemoRunProgressStep]
    job_id: Optional[str] = None
    position_id: Optional[str] = None
    result: Optional[DemoRunResponse] = None
    error: Optional[str] = None


class FullDemoRunRequest(BaseModel):
    composite: str = Field(..., min_length=2)
    region: Region
    iso_hour: int = Field(..., ge=0, le=23)
    sla: SLA
    tier: Tier
    quantity_ngh: float = Field(10.0, gt=0)
    price_per_ngh: float = Field(2.45, gt=0)
    package_size_ngh: float = Field(10.0, gt=0, le=15.0)
    job_id: Optional[str] = None
    gpu_model_label: str = Field("demo-workload", min_length=1, max_length=64)
    target_settle_seconds: int = Field(300, ge=30, le=31_622_400)


class FullDemoRunStartResponse(BaseModel):
    run_id: str


class MarketLiveOverviewRow(BaseModel):
    gpu_model: str
    product_key: ProductKey
    last_price_per_ngh: float = Field(..., ge=0)
    best_bid_per_ngh: Optional[float] = Field(None, ge=0)
    best_ask_per_ngh: Optional[float] = Field(None, ge=0)
    spread_per_ngh: Optional[float] = Field(None, ge=0)
    traded_volume_ngh_5m: float = Field(..., ge=0)
    """Resting bid+ask size (NGH) on the book — moves with simulated liquidity."""
    book_depth_ngh: float = Field(0.0, ge=0)
    active_order_count: int = Field(..., ge=0)


class MarketLiveOverviewResponse(BaseModel):
    as_of: str
    rows: List[MarketLiveOverviewRow]


class MarketSimulationStartRequest(BaseModel):
    synthetic_buyer_agents: int = Field(30, ge=1, le=500)
    synthetic_seller_agents: int = Field(20, ge=1, le=500)
    ticks_per_second: float = Field(2.0, ge=0.2, le=20.0)


class MarketSimulationStatusResponse(BaseModel):
    running: bool
    synthetic_buyer_agents: int = Field(..., ge=0)
    synthetic_seller_agents: int = Field(..., ge=0)
    ticks_per_second: float = Field(..., ge=0)
    started_at: Optional[str] = None
    total_ticks: int = Field(..., ge=0)
    total_synthetic_orders: int = Field(..., ge=0)


class TradingSubaccountRiskResponse(BaseModel):
    owner_id: str
    subaccount_id: str
    max_order_notional: float = Field(..., gt=0)
    kill_switch_enabled: bool
    updated_at: str


class TradingSubaccountRiskUpdateRequest(BaseModel):
    subaccount_id: str = Field(..., min_length=1, max_length=64)
    max_order_notional: float = Field(..., gt=0)
    kill_switch_enabled: bool = False


class TradingHierarchyResponse(BaseModel):
    owner_id: str
    org_id: str
    account_id: str
    subaccounts: List[TradingSubaccountRiskResponse]
    updated_at: str


class FeasibilityResponse(BaseModel):
    """Response model for job feasibility check"""

    ngh_required: float = Field(..., description="Sum of package size estimates in NGH")
    earliest_start: str = Field(
        ...,
        description="Next feasible window given artifact sizes and Standard prepare rules (ISO 8601 format)",
    )
    voucher_gap: float = Field(
        ..., description="NGH required minus vouchers already deposited for the key"
    )
    milestone_sanity: Dict[str, bool] = Field(
        ...,
        description="Flags for milestone sanity checks: first_output_ok, size_band_ok",
    )


class RelayLink(BaseModel):
    """Relay link for manifest access"""

    manifest_url: str = Field(..., description="URL to access the manifest")
    expires_at: Optional[str] = Field(
        None, description="Expiration time in ISO 8601 format"
    )


class JobResponse(BaseModel):
    """Response model for job status"""

    job_id: str
    status: JobStatus
    window: Window
    package_index: List[PackageDescriptor]
    created_at: str = Field(..., description="Job creation timestamp in ISO 8601 format")
    relay_links: Optional[List[RelayLink]] = Field(
        None, description="Relay links for manifests"
    )
    created_by: Optional[str] = Field(
        None, description="User ID of the buyer who created the job"
    )


# Provider-side models


class NominationRequest(BaseModel):
    """Request model for provider to declare NGH availability"""

    region: Region
    iso_hour: int = Field(..., ge=0, le=23, description="ISO hour (0-23)")
    tier: Tier
    sla: SLA
    ngh_available: float = Field(..., gt=0, description="NGH available for this window")
    gpu_model: str = Field("RTX 4090", min_length=1, max_length=64)
    gpu_count: int = Field(1, ge=1, le=64)


class NominationResponse(BaseModel):
    """Response model for nomination"""

    nomination_id: str = Field(..., description="Unique identifier for the nomination")
    region: Region
    iso_hour: int
    tier: Tier
    sla: SLA
    ngh_available: float
    gpu_model: str = "RTX 4090"
    gpu_count: int = 1
    provider_id: Optional[str] = None
    created_at: str = Field(
        ..., description="Nomination creation timestamp in ISO 8601 format"
    )


class MarketplaceGpuListingResponse(BaseModel):
    listing_id: str
    provider_id: str
    gpu_model: str
    gpu_count: int = Field(..., ge=1)
    region: Region
    iso_hour: int = Field(..., ge=0, le=23)
    tier: Tier
    sla: SLA
    ngh_available: float = Field(..., ge=0)
    indicative_price_per_ngh: float = Field(..., ge=0)
    created_at: str


class LotStatus(str, Enum):
    """Lot status enumeration"""

    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LotCreateRequest(BaseModel):
    """Request model for creating a lot"""

    window: Window
    job_id: Optional[str] = Field(
        None, description="Optional job ID to associate with this lot"
    )


class Lot(BaseModel):
    """Model for a compute lot"""

    lot_id: str
    status: LotStatus
    job_id: Optional[str] = Field(None, description="Associated job ID if assigned")
    window: Window
    created_at: str = Field(..., description="Lot creation timestamp in ISO 8601 format")
    provider_id: Optional[str] = Field(
        None, description="User ID of the provider who owns this lot"
    )
    prepared_at: Optional[str] = Field(
        None, description="Preparation ready timestamp in ISO 8601 format"
    )
    completed_at: Optional[str] = Field(
        None, description="Completion timestamp in ISO 8601 format"
    )
    # Result fields
    output_root: Optional[str] = Field(None, description="Root hash or URI of output")
    item_count: Optional[int] = Field(None, description="Number of items processed")
    wall_time_seconds: Optional[float] = Field(
        None, description="Wall clock time in seconds"
    )
    raw_gpu_time_seconds: Optional[float] = Field(None, description="Raw GPU time in seconds")
    logs_uri: Optional[str] = Field(None, description="URI to access logs")


class PrepareReadyRequest(BaseModel):
    """Request model for attesting lot readiness"""

    device_ok: bool = Field(..., description="Device is operational")
    driver_ok: bool = Field(..., description="Driver is operational")
    image_pulled: bool = Field(..., description="Container image has been pulled")
    inputs_prefetched: bool = Field(..., description="Inputs have been prefetched")


class PrepareReadyResponse(BaseModel):
    """Response model for prepare ready"""

    lot_id: str
    status: LotStatus
    prepared_at: str = Field(
        ..., description="Preparation ready timestamp in ISO 8601 format"
    )


class ResultRequest(BaseModel):
    """Request model for submitting lot results"""

    output_root: str = Field(..., description="Root hash or URI of output")
    item_count: int = Field(..., ge=0, description="Number of items processed")
    wall_time_seconds: float = Field(..., gt=0, description="Wall clock time in seconds")
    raw_gpu_time_seconds: float = Field(..., gt=0, description="Raw GPU time in seconds")
    logs_uri: Optional[str] = Field(None, description="URI to access logs")


class ResultResponse(BaseModel):
    """Response model for result submission"""

    lot_id: str
    status: LotStatus
    output_root: str
    item_count: int
    wall_time_seconds: float
    raw_gpu_time_seconds: float
    logs_uri: Optional[str]
    completed_at: str = Field(..., description="Completion timestamp in ISO 8601 format")

