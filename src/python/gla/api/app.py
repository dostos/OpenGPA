"""GLA FastAPI application factory.

MUST be served on 127.0.0.1 only (NFR-5.1 — localhost-only binding).
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


def create_app(query_engine, engine=None, auth_token: str = "",
               scene_reconstructor=None) -> FastAPI:
    """Create and configure the GLA REST API application.

    Args:
        query_engine: A QueryEngine instance (or compatible mock) for frame queries.
        engine: Optional Engine instance for pause/resume/step control.
        auth_token: Bearer token required on every request. Empty string disables auth.
        scene_reconstructor: Optional SceneReconstructor instance. A default one is
            created automatically when not provided.

    Returns:
        Configured FastAPI application. Bind to 127.0.0.1 when serving.
    """
    app = FastAPI(title="GLA", version="0.1.0")

    app.state.query_engine = query_engine
    app.state.engine = engine
    app.state.auth_token = auth_token

    if scene_reconstructor is None:
        try:
            from _gla_core import SceneReconstructor  # type: ignore
            scene_reconstructor = SceneReconstructor()
        except ImportError:
            scene_reconstructor = None

    app.state.scene_reconstructor = scene_reconstructor

    @app.middleware("http")
    async def check_auth(request: Request, call_next):
        raw_header = request.headers.get("Authorization", "")
        token = raw_header.removeprefix("Bearer ").strip()
        if token != request.app.state.auth_token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token"},
            )
        return await call_next(request)

    from .routes_frames import router as frames_router
    from .routes_drawcalls import router as drawcalls_router
    from .routes_pixel import router as pixel_router
    from .routes_control import router as control_router
    from .routes_scene import router as scene_router
    from .routes_diff import router as diff_router

    app.include_router(frames_router, prefix="/api/v1")
    app.include_router(drawcalls_router, prefix="/api/v1")
    app.include_router(pixel_router, prefix="/api/v1")
    app.include_router(control_router, prefix="/api/v1")
    app.include_router(scene_router, prefix="/api/v1")
    app.include_router(diff_router, prefix="/api/v1")

    return app
