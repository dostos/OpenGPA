"""REST endpoints for pixel explanation."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["explain"])


@router.get("/frames/{frame_id}/explain/{x}/{y}")
async def explain_pixel(frame_id: int, x: int, y: int, request: Request):
    fqe = request.app.state.framework_query_engine
    if not fqe:
        raise HTTPException(status_code=501, detail="Framework query engine not configured")
    explanation = fqe.explain_pixel(frame_id, x, y)
    if not explanation:
        raise HTTPException(status_code=404, detail="No pixel explanation available")
    return asdict(explanation)
