from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.repositories.memory.storage import storage
from app.schemas.models import (
    CollectiveSessionCreateRequest,
    CollectiveSessionResponse,
    SessionFinalizeResponse,
)

router = APIRouter()


@router.post(
    "/sessions",
    response_model=CollectiveSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(body: CollectiveSessionCreateRequest):
    try:
        return storage.create_collective_session(body)
    except ValueError as exc:
        msg = str(exc)
        if msg == "session_already_exists":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
        if msg == "job_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        if msg == "world_size_less_than_membership":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
        raise


@router.get("/sessions", response_model=List[CollectiveSessionResponse])
def list_sessions(job_id: Optional[str] = Query(None)):
    return storage.list_collective_sessions(job_id=job_id)


@router.get("/sessions/{session_id}", response_model=CollectiveSessionResponse)
def get_session(session_id: str):
    row = storage.get_collective_session(session_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session_not_found")
    return row


@router.post("/sessions/{session_id}/finalize", response_model=SessionFinalizeResponse)
def finalize_session(session_id: str):
    try:
        return storage.finalize_collective_session(session_id)
    except ValueError as exc:
        msg = str(exc)
        if msg == "session_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
