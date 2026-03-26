from fastapi import APIRouter

from app.gpu_backend_config import (
    factoring_base_url,
    factoring_post_url,
    factoring_ssh_host_label,
    probe_gpu_backend_tcp,
    setup_instructions_hint,
)
from app.repositories.memory.storage import storage
from app.schemas.models import GpuBackendStatusResponse, PlatformStatusResponse


router = APIRouter()


def _requests_installed() -> bool:
    try:
        import requests  # noqa: F401
    except Exception:
        return False
    return True


@router.get("/platform/gpu-backend", response_model=GpuBackendStatusResponse)
def get_gpu_backend_status():
    """Whether the CoreIndex API can reach the remote GPU factoring HTTP service (TCP probe)."""
    tcp_ok, tcp_err = probe_gpu_backend_tcp()
    return GpuBackendStatusResponse(
        configured_base_url=factoring_base_url(),
        factor_post_url=factoring_post_url(),
        ssh_host_label=factoring_ssh_host_label(),
        tcp_reachable=tcp_ok,
        tcp_error=tcp_err,
        requests_installed=_requests_installed(),
        setup_hint=setup_instructions_hint(),
    )


@router.get("/platform/status", response_model=PlatformStatusResponse)
def get_platform_status():
    """
    Return visible platform metadata for the frontend shell.

    This endpoint is intentionally lightweight and product-facing. It gives the
    UI one stable place to discover active platform capabilities and recent
    event activity.
    """
    return PlatformStatusResponse(
        current_phase="live",
        current_focus="Persistent market, execution, funding, and derivatives workflows",
        api_version="1.0.0",
        capabilities=[
            "auth",
            "auth_persistence",
            "market_positions",
            "jobs",
            "feasibility",
            "voucher_balances",
            "voucher_deposit",
            "provider_nominations",
            "lots",
            "qc_hashing",
            "qc_certificates",
            "platform_status",
            "state_persistence",
            "options_pricing",
            "options_contracts",
            "options_orderbook",
            "risk_limits",
            "order_amend_cancel",
            "time_in_force",
            "portfolio_blotter",
            "margin_stress_test",
            "liquidation_simulation",
            "provider_sla_dashboard",
            "risk_profile_controls",
            "kill_switch",
            "execution_quality_metrics",
            "strategy_routing",
            "strategy_risk_limits",
            "provider_fleet_overview",
            "pretrade_explainability",
            "compute_delivery_orchestration",
            "account_hierarchy_controls",
            "provider_split_demo_run",
            "local_evm_anchor",
            "auto_provider_matching",
            "dynamic_gpu_count_matching",
            "market_simulation_engine",
            "live_market_data_feed",
            "one_click_demo_progress",
        ],
        event_count=storage.event_count(),
        recent_events=storage.list_events(limit=8),
    )
