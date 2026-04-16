"""Capture engine control endpoints (pause / resume / step / status)."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["control"])


def _engine_or_404(request: Request):
    engine = request.app.state.engine
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not attached")
    return engine


@router.post("/control/pause")
def pause_engine(request: Request) -> Dict[str, Any]:
    """Pause frame capture."""
    engine = _engine_or_404(request)
    engine.pause()
    return {"status": "paused"}


@router.post("/control/resume")
def resume_engine(request: Request) -> Dict[str, Any]:
    """Resume frame capture."""
    engine = _engine_or_404(request)
    engine.resume()
    return {"status": "running"}


@router.post("/control/step")
def step_engine(
    request: Request,
    count: int = Query(1, ge=1, description="Number of frames to advance"),
) -> Dict[str, Any]:
    """Advance capture by *count* frames (only valid while paused)."""
    engine = _engine_or_404(request)
    engine.step(count)
    return {"status": "stepped", "count": count}


@router.get("/control/status")
def get_status(request: Request) -> Dict[str, Any]:
    """Return the current engine running state."""
    engine = _engine_or_404(request)
    is_running = engine.is_running()
    return {
        "state": "running" if is_running else "paused",
        "is_running": is_running,
    }
