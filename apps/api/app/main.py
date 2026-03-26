import asyncio
import concurrent.futures
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load apps/api/.env before any settings that read os.environ (FACTORING_REMOTE_HTTP_URL, etc.).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.schemas.models import MarketSimulationStartRequest
from app.services.market_simulator import market_simulator

app = FastAPI(
    title="Compute Market Exchange API",
    description="API for compute market exchange - buyer and provider endpoints",
    version="1.0.0"
)

# CORS: wildcard + credentials is invalid in browsers; list local dev origins explicitly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.on_event("startup")
def _expand_default_threadpool():
    """Avoid starving sync route handlers when the UI fans out many feasibility calls."""
    try:
        loop = asyncio.get_running_loop()
        loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=80))
    except Exception:
        logging.getLogger("uvicorn.error").warning(
            "Could not expand default ThreadPoolExecutor", exc_info=True
        )


@app.on_event("startup")
def _log_gpu_factoring_config():
    try:
        from app.gpu_backend_config import factoring_post_url, probe_gpu_backend_tcp

        ok, terr = probe_gpu_backend_tcp()
        logging.getLogger("uvicorn.error").info(
            "GPU factoring: POST %s | tcp_reachable=%s%s",
            factoring_post_url(),
            ok,
            f" ({terr})" if terr else "",
        )
    except Exception:
        logging.getLogger("uvicorn.error").warning(
            "Could not probe GPU factoring endpoint", exc_info=True
        )


@app.on_event("startup")
def _startup_market_simulator():
    # Keep the advanced market view active by default for demo sessions.
    try:
        market_simulator.start(
            MarketSimulationStartRequest(
                synthetic_buyer_agents=24,
                synthetic_seller_agents=16,
                ticks_per_second=1.25,
            )
        )
    except Exception:
        logging.getLogger("uvicorn.error").warning(
            "market_simulator.start failed; API will run without synthetic agents",
            exc_info=True,
        )


@app.on_event("startup")
def _demo_voucher_wallet_topup():
    raw = os.getenv("DEMO_VOUCHER_WALLET_NGH", "").strip()
    if not raw:
        return
    try:
        amount = float(raw)
    except ValueError:
        logging.getLogger("uvicorn.error").warning(
            "Invalid DEMO_VOUCHER_WALLET_NGH=%r (expected a number)", raw
        )
        return
    if amount < 0:
        return
    fill_hours = os.getenv("DEMO_VOUCHER_FILL_TEMPLATE_HOURS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        from app.repositories.memory.storage import storage

        storage.apply_demo_voucher_wallet_topup(amount, fill_template_hours=fill_hours)
        logging.getLogger("uvicorn.error").info(
            "Demo voucher wallets set to %.0f NGH (fill_template_hours=%s)",
            amount,
            fill_hours,
        )
    except Exception:
        logging.getLogger("uvicorn.error").warning(
            "DEMO_VOUCHER_WALLET_NGH top-up failed", exc_info=True
        )


@app.on_event("shutdown")
def _shutdown_market_simulator():
    market_simulator.stop()


@app.on_event("shutdown")
def _flush_storage_snapshot():
    try:
        from app.repositories.memory.storage import storage

        storage.flush_persist_blocking()
    except Exception:
        logging.getLogger("uvicorn.error").warning(
            "Could not flush storage snapshot on shutdown", exc_info=True
        )


@app.get("/")
def health():
    return {"status": "ok"}
