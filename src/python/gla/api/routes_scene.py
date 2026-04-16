"""Scene query endpoints: full scene, camera, and objects."""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["scene"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_normalized_frame(qe, frame_id: int):
    """Return (overview, normalized_frame) or raise 404."""
    overview = qe.frame_overview(frame_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    frame = qe.get_normalized_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Normalized frame {frame_id} not found")
    return frame


def _camera_to_dict(cam) -> Dict[str, Any]:
    """Convert a CameraInfo object (real or mock) to a JSON-serialisable dict."""
    pos = list(cam.position)
    fwd = list(cam.forward)
    up  = list(cam.up)
    cam_type = "perspective" if cam.is_perspective else "orthographic"
    summary = (
        f"{cam_type.capitalize()} camera at "
        f"({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f}) looking toward "
        f"({fwd[0]:.3f}, {fwd[1]:.3f}, {fwd[2]:.3f}), "
        f"FOV {cam.fov_y_degrees:.1f} deg"
    )
    return {
        "summary": summary,
        "position": pos,
        "forward": fwd,
        "up": up,
        "fov_y_degrees": cam.fov_y_degrees,
        "aspect_ratio": cam.aspect,
        "near": cam.near_plane,
        "far": cam.far_plane,
        "type": cam_type,
        "confidence": cam.confidence,
    }


def _object_to_dict(obj) -> Dict[str, Any]:
    """Convert a SceneObject (real or mock) to a JSON-serialisable dict."""
    return {
        "id": obj.id,
        "draw_call_ids": list(obj.draw_call_ids),
        "world_transform": list(obj.world_transform),
        "bounding_box": {
            "min": list(obj.bbox_min),
            "max": list(obj.bbox_max),
        },
        "visible": obj.visible,
        "confidence": obj.confidence,
    }


def _reconstruct(request: Request, frame_id: int):
    """Run SceneReconstructor and return SceneInfo, or raise 404."""
    qe = request.app.state.query_engine
    reconstructor = request.app.state.scene_reconstructor

    overview = qe.frame_overview(frame_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")

    frame = qe.get_normalized_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Normalized frame {frame_id} not found")

    return reconstructor.reconstruct(frame)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/frames/{frame_id}/scene")
def get_scene(frame_id: int, request: Request) -> Dict[str, Any]:
    """Full scene reconstruction: camera + objects + quality."""
    scene = _reconstruct(request, frame_id)
    result: Dict[str, Any] = {
        "reconstruction_quality": scene.reconstruction_quality,
    }
    if scene.camera is not None:
        result["camera"] = _camera_to_dict(scene.camera)
    else:
        result["camera"] = None
    result["objects"] = [_object_to_dict(o) for o in scene.objects]
    return result


@router.get("/frames/{frame_id}/scene/camera")
def get_camera(frame_id: int, request: Request) -> Dict[str, Any]:
    """Camera parameters for a frame."""
    scene = _reconstruct(request, frame_id)
    if scene.camera is None:
        raise HTTPException(status_code=404, detail="Camera could not be extracted for this frame")
    return _camera_to_dict(scene.camera)


@router.get("/frames/{frame_id}/scene/objects")
def get_objects(frame_id: int, request: Request) -> Dict[str, Any]:
    """List scene objects with transforms and bounding boxes."""
    scene = _reconstruct(request, frame_id)
    return {
        "objects": [_object_to_dict(o) for o in scene.objects],
        "reconstruction_quality": scene.reconstruction_quality,
    }
