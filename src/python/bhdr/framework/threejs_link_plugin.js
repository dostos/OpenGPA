// threejs_link_plugin.js — OpenGPA Tier-3 link plugin for three.js
//
// Walks `scene.traverse()` once per render(), pushes a debug-marker per
// Mesh/Light/Group around the corresponding GL draw calls, and POSTs the
// flattened scene tree to the engine annotations endpoint so that
// `gpa scene-find` and `gpa explain-draw` can join GL draws back to
// framework objects.
//
// Drop-in usage (HTML page):
//   <script type="module">
//     import * as THREE from 'three';
//     import { installGpaLinkPlugin } from './threejs_link_plugin.js';
//     const renderer = new THREE.WebGLRenderer();
//     const scene    = new THREE.Scene();
//     installGpaLinkPlugin({
//       scene, renderer,
//       endpoint: 'http://localhost:18080',
//       token:    window.BHDR_AUTH_TOKEN,
//     });
//     renderer.render(scene, camera); // plugin tags + POSTs automatically
//   </script>
//
// Reads `window.BHDR_AUTH_TOKEN` and `window.BHDR_FRAME_ID` (if set);
// falls back to the values passed in `options`. Never blocks the render
// loop — POST is deferred to requestAnimationFrame; failures are
// swallowed so a misconfigured engine never breaks the host page.

const PLUGIN_NAME = "threejs-link";
const PLUGIN_VERSION = "0.1";
const FRAMEWORK = "three.js";

function _serializeNode(obj, parentPath) {
  const own =
    obj.name && obj.name.length > 0
      ? obj.name
      : (obj.uuid || obj.type || "anon");
  const path = parentPath ? `${parentPath}/${own}` : own;
  const node = {
    path,
    uuid: obj.uuid,
    name: obj.name || null,
    type: obj.type || "Object3D",
    visible: !!obj.visible,
    castShadow: !!obj.castShadow,
    frustumCulled: !!obj.frustumCulled,
    position: _vec3(obj.position),
    rotation: _vec4(obj.quaternion),
    scale: _vec3(obj.scale),
    draw_call_ids: [],
  };
  if (obj.material) {
    const m = Array.isArray(obj.material) ? obj.material[0] : obj.material;
    if (m) {
      node.material = {
        name: m.name || null,
        type: m.type || "Material",
        transparent: !!m.transparent,
        opacity: typeof m.opacity === "number" ? m.opacity : 1.0,
        map_texture_id: m.map && typeof m.map.id === "number" ? m.map.id : null,
      };
    }
  }
  if (obj.geometry) {
    const g = obj.geometry;
    if (typeof g.computeBoundingSphere === "function") {
      try { g.computeBoundingSphere(); } catch (e) { /* ignore */ }
    }
    node.geometry = {
      type: g.type || "BufferGeometry",
      vertex_count:
        g.attributes && g.attributes.position
          ? g.attributes.position.count || 0
          : 0,
      bounding_sphere_radius:
        g.boundingSphere && typeof g.boundingSphere.radius === "number"
          ? g.boundingSphere.radius
          : 0,
    };
  }
  return [node, path];
}

function _vec3(v) {
  if (!v || typeof v.x !== "number") return null;
  return [v.x, v.y, v.z];
}

function _vec4(v) {
  if (!v || typeof v.x !== "number") return null;
  return [v.x, v.y, v.z, typeof v.w === "number" ? v.w : 0];
}

function _collectScene(root) {
  const out = [];
  // Use parent links to build correct paths.
  const pathByUuid = new Map();
  root.traverse((obj) => {
    const parentPath = obj.parent ? pathByUuid.get(obj.parent.uuid) || "" : "";
    const [node, path] = _serializeNode(obj, parentPath);
    pathByUuid.set(obj.uuid, path);
    out.push(node);
  });
  return out;
}

function _post(endpoint, frameId, token, body) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(`${endpoint}/api/v1/frames/${frameId}/annotations`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  }).catch(() => { /* never break the render loop */ });
}

export function installGpaLinkPlugin(options) {
  const { scene, renderer } = options || {};
  if (!scene || !renderer) {
    console.warn("[bhdr-threejs-link] scene/renderer missing; plugin disabled");
    return;
  }
  const endpoint =
    options.endpoint ||
    (typeof window !== "undefined" && window.BHDR_ENDPOINT) ||
    "http://localhost:18080";
  const token =
    options.token ||
    (typeof window !== "undefined" && window.BHDR_AUTH_TOKEN) ||
    "";

  let frameCounter =
    typeof options.frameId === "number"
      ? options.frameId
      : (typeof window !== "undefined" && typeof window.BHDR_FRAME_ID === "number"
         ? window.BHDR_FRAME_ID
         : 0);

  const gl = (renderer.getContext && renderer.getContext()) || null;
  const hasDebugGroups =
    !!gl &&
    typeof gl.pushDebugGroup === "function" &&
    typeof gl.popDebugGroup === "function";

  // Wrap renderer.render with per-mesh debug markers around the inner
  // draw calls. The wrapping uses onBeforeRender / onAfterRender hooks
  // (built-in three.js callbacks) so we don't have to monkey-patch the
  // private renderObject pipeline.
  scene.traverse((obj) => {
    if (obj.userData && obj.userData.__gpaLinkInstrumented) return;
    obj.userData = obj.userData || {};
    obj.userData.__gpaLinkInstrumented = true;
    const _origBefore = obj.onBeforeRender;
    const _origAfter = obj.onAfterRender;
    obj.onBeforeRender = function (rndr, scn, cam, geom, mat, group) {
      if (hasDebugGroups) {
        try {
          gl.pushDebugGroup(0x824b /* GL_DEBUG_SOURCE_APPLICATION */, 0,
                            (obj.name || obj.uuid || "node"));
        } catch (e) { /* ignore */ }
      }
      if (typeof _origBefore === "function") {
        _origBefore.call(this, rndr, scn, cam, geom, mat, group);
      }
    };
    obj.onAfterRender = function (rndr, scn, cam, geom, mat, group) {
      if (typeof _origAfter === "function") {
        _origAfter.call(this, rndr, scn, cam, geom, mat, group);
      }
      if (hasDebugGroups) {
        try { gl.popDebugGroup(); } catch (e) { /* ignore */ }
      }
    };
  });

  const _origRender = renderer.render.bind(renderer);
  renderer.render = function (s, cam) {
    _origRender(s, cam);
    const fid = frameCounter;
    frameCounter += 1;
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(() => {
        const payload = {
          [PLUGIN_NAME]: {
            plugin: PLUGIN_NAME,
            plugin_version: PLUGIN_VERSION,
            framework: FRAMEWORK,
            framework_version:
              (typeof window !== "undefined" &&
               window.THREE &&
               window.THREE.REVISION) || "unknown",
            renderer: {
              outputColorSpace: renderer.outputColorSpace,
              toneMapping: renderer.toneMapping,
              autoClear: renderer.autoClear,
              shadowMap: {
                enabled: renderer.shadowMap && renderer.shadowMap.enabled,
                type: renderer.shadowMap && renderer.shadowMap.type,
              },
              pixelRatio:
                typeof renderer.getPixelRatio === "function"
                  ? renderer.getPixelRatio()
                  : 1.0,
            },
            scene: _collectScene(scene),
          },
        };
        _post(endpoint, fid, token, payload);
      });
    }
  };
  return {
    name: PLUGIN_NAME,
    version: PLUGIN_VERSION,
    framework: FRAMEWORK,
  };
}

// Also expose under window for non-module loaders.
if (typeof window !== "undefined") {
  window.installGpaLinkPlugin = installGpaLinkPlugin;
}
