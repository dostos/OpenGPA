"""Dataclass types for framework-level scene graph concepts.

These are populated by framework plugins (e.g. Three.js, Unity, Unreal) that
POST metadata alongside captured GPU frames.  The result types (ObjectInfo,
RenderPassInfo, MaterialInfo, PixelExplanation) are used by the query engine
in Task 6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Framework input types — populated from POST /api/v1/frames/{id}/metadata
# ---------------------------------------------------------------------------

@dataclass
class FrameworkObject:
    name: str
    type: str = ""
    parent: str = ""
    draw_call_ids: List[int] = field(default_factory=list)
    transform: Dict[str, Any] = field(default_factory=dict)
    visible: bool = True
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FrameworkMaterial:
    name: str
    shader: str = ""
    used_by: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    textures: Dict[str, str] = field(default_factory=dict)


@dataclass
class FrameworkRenderPass:
    name: str
    draw_call_range: List[int] = field(default_factory=list)
    output: Any = None
    input: List[str] = field(default_factory=list)


@dataclass
class FrameMetadata:
    framework: str = ""
    version: str = ""
    objects: List[FrameworkObject] = field(default_factory=list)
    materials: List[FrameworkMaterial] = field(default_factory=list)
    render_passes: List[FrameworkRenderPass] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Query result types — used by the query engine (Task 6)
# ---------------------------------------------------------------------------

@dataclass
class ObjectInfo:
    name: str
    type: str
    parent: str
    draw_call_ids: List[int]
    material: Optional[str]
    transform: Dict[str, Any]
    visible: bool
    properties: Dict[str, Any]


@dataclass
class RenderPassInfo:
    name: str
    draw_call_ids: List[int]
    input: List[str]
    output: Any


@dataclass
class MaterialInfo:
    name: str
    shader: str
    properties: Dict[str, Any]
    textures: Dict[str, str]
    used_by: List[str]


@dataclass
class PixelExplanation:
    pixel: Dict[str, Any]
    draw_call_id: Optional[int]
    debug_group: Optional[str]
    render_pass: Optional[str]
    object: Optional[Dict[str, Any]]
    material: Optional[Dict[str, Any]]
    shader_params: List[Dict[str, Any]]
    data_sources: List[str]
