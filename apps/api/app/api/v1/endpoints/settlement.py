from __future__ import annotations

import hashlib
import json
import os

from fastapi import APIRouter, HTTPException, status

from app.repositories.memory.storage import storage
from app.schemas.models import (
    SettlementAnchorRequest,
    SettlementOnchainVerifyResponse,
    SettlementPayRequest,
    SettlementRunResponse,
)

router = APIRouter()


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _anchor_to_local_evm(anchor_hash: str) -> dict:
    rpc_url = os.getenv("LOCAL_EVM_RPC_URL", "http://127.0.0.1:8545")
    explorer_base = os.getenv("LOCAL_EVM_EXPLORER_BASE", "").rstrip("/")

    try:
        import requests
    except Exception:
        synthetic_hash = "0x" + _hash_payload({"rpc_url": rpc_url, "anchor_hash": anchor_hash})[:64]
        return {
            "network_label": "local-evm-simulated",
            "tx_hash": synthetic_hash,
            "block_number": None,
            "explorer_url": None,
        }

    def rpc(method: str, params: list):
        resp = requests.post(
            rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(str(data["error"]))
        return data["result"]

    try:
        accounts = rpc("eth_accounts", [])
        if not accounts:
            raise RuntimeError("No unlocked account on local EVM")
        from_addr = os.getenv("LOCAL_EVM_FROM", accounts[0])
        tx_hash = rpc(
            "eth_sendTransaction",
            [
                {
                    "from": from_addr,
                    "to": from_addr,
                    "value": "0x0",
                    "data": "0x" + anchor_hash[:64],
                }
            ],
        )
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        block_hex = receipt.get("blockNumber") if isinstance(receipt, dict) else None
        block_number = int(block_hex, 16) if block_hex else None
        explorer_url = f"{explorer_base}/tx/{tx_hash}" if explorer_base else None
        return {
            "network_label": "local-evm",
            "tx_hash": tx_hash,
            "block_number": block_number,
            "explorer_url": explorer_url,
        }
    except Exception:
        synthetic_hash = "0x" + _hash_payload({"rpc_url": rpc_url, "anchor_hash": anchor_hash})[:64]
        return {
            "network_label": "local-evm-simulated",
            "tx_hash": synthetic_hash,
            "block_number": None,
            "explorer_url": None,
        }


def _verify_anchor_onchain(anchor_hash: str, tx_hash: str) -> tuple[bool, bool, str | None, int | None]:
    rpc_url = os.getenv("LOCAL_EVM_RPC_URL", "http://127.0.0.1:8545")
    try:
        import requests
    except Exception:
        return False, False, "requests_not_installed", None

    try:
        resp = requests.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getTransactionByHash",
                "params": [tx_hash],
            },
            timeout=5,
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            return False, True, f"rpc_error:{body['error']}", None
        tx = body.get("result")
        if not isinstance(tx, dict):
            return False, True, "tx_not_found", None
        data_field = str(tx.get("input") or tx.get("data") or "")
        expected = "0x" + anchor_hash[:64]
        if not data_field.startswith("0x"):
            return False, True, "tx_data_missing", None
        if data_field.lower() != expected.lower():
            return False, True, "anchor_hash_mismatch", None

        rec = requests.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getTransactionReceipt",
                "params": [tx_hash],
            },
            timeout=5,
        )
        rec.raise_for_status()
        rec_body = rec.json()
        receipt = rec_body.get("result") if isinstance(rec_body, dict) else None
        block_hex = receipt.get("blockNumber") if isinstance(receipt, dict) else None
        block_number = int(block_hex, 16) if block_hex else None
        return True, True, None, block_number
    except Exception as exc:
        return False, False, str(exc), None


@router.post(
    "/settlement/anchor",
    response_model=SettlementRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def anchor_settlement(body: SettlementAnchorRequest):
    try:
        row = storage.create_settlement_anchor(body)
        anchor_hash = _hash_payload(
            {
                "settlement_id": row.settlement_id,
                "job_id": row.job_id,
                "receipt_root": row.receipt_root,
                "qc_root": row.qc_root,
            }
        )
        blockchain_anchor = _anchor_to_local_evm(anchor_hash)
        return storage.set_settlement_onchain_anchor(
            row.settlement_id,
            anchor_hash=anchor_hash,
            blockchain_anchor=blockchain_anchor,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "job_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.post("/settlement/pay", response_model=SettlementRunResponse)
def pay_settlement(body: SettlementPayRequest):
    try:
        return storage.settle_job(body)
    except ValueError as exc:
        msg = str(exc)
        if msg in ("settlement_not_found", "settlement_job_mismatch"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


@router.get(
    "/settlement/{settlement_id}/verify_onchain",
    response_model=SettlementOnchainVerifyResponse,
)
def verify_settlement_onchain(settlement_id: str):
    row = storage.get_settlement_run(settlement_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="settlement_not_found")
    tx_hash = None
    if isinstance(row.blockchain_anchor, dict):
        tx_hash = row.blockchain_anchor.get("tx_hash")
    if not row.anchor_hash or not isinstance(tx_hash, str) or not tx_hash:
        return SettlementOnchainVerifyResponse(
            settlement_id=settlement_id,
            tx_hash=tx_hash if isinstance(tx_hash, str) else None,
            chain_reachable=False,
            verified=False,
            reason="settlement_missing_anchor",
            block_number=None,
        )
    verified, reachable, reason, block_number = _verify_anchor_onchain(row.anchor_hash, tx_hash)
    return SettlementOnchainVerifyResponse(
        settlement_id=settlement_id,
        tx_hash=tx_hash,
        chain_reachable=reachable,
        verified=verified,
        reason=reason,
        block_number=block_number,
    )
