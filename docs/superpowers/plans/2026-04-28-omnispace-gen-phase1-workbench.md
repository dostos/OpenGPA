# omnispace-gen Phase 1: Workbench Tier-3 Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire OpenGPA's Tier-3 metadata sidecar into omnispace-gen's Three.js workbench so an agent can run `query_object("joint_<smplx_name>")` against MCP and read each joint's world transform from the rendered scene.

**Architecture:** Extract OpenGPA's existing Three.js plugin into a publishable client package (`clients/threejs/`). In omnispace-gen, consume the existing `SkeletonRegistry` for canonical joint names, expose them to the workbench via a generated TS file, render named joint markers as a new R3F component, and instantiate the sidecar in `Viewer3D`'s `<Canvas onCreated>` callback.

**Tech Stack:** TypeScript / React / `@react-three/fiber` (workbench), Python (joint name shim + build script), vanilla JS (extracted Three.js client), pytest + jest + Playwright.

**Spec:** `docs/superpowers/specs/2026-04-28-omnispace-gen-integration-design.md`

**Cross-repo:** This plan touches two repositories.
- `gla/` (OpenGPA): extract reusable Three.js client.
- `omnispace-gen/`: consume the client; add joint markers, sidecar wiring, build script, tests.

**Out of scope (deferred to Plan B / Phase 2):**
- Open3D Tier-3 sidecar.
- Python `clients/python/` package extraction.
- Eval scenario `tests/eval/r37_joint_offset_smplx/` (full agent-loop diagnosis).
- OSMesa shim, `readPixels` bridge (Phase 3, conditional).

**Definition of done:** With workbench running locally and OpenGPA engine on `:18080`, toggling "OpenGPA capture" in the workbench UI, generating a motion, and running `curl :18080/api/v1/frames/0/objects` returns the canonical SMPLX joint markers with the correct names — and the corresponding world transforms match the underlying `MotionSequence.joints`.

---

## File Structure

**OpenGPA repo (`gla/`):**

| File | Action | Responsibility |
|---|---|---|
| `clients/threejs/index.js` | Create | The `OpenGPAThreePlugin` class (moved from `src/shims/webgl/extension/bhdr-threejs-plugin.js`). |
| `clients/threejs/package.json` | Create | `@opengpa/threejs-sidecar` package metadata. ES module, no runtime deps. |
| `clients/threejs/README.md` | Create | Quickstart: install, instantiate after renderer, call `capture(scene, camera)` after each render. |
| `clients/threejs/test.js` | Create | Smoke test: module loads, `capture()` POSTs to a stub server with documented payload shape. |
| `src/shims/webgl/extension/bhdr-threejs-plugin.js` | Modify | Becomes a one-line re-export from `clients/threejs/index.js` so the Chrome extension still works unchanged. |

**omnispace-gen repo:**

| File | Action | Responsibility |
|---|---|---|
| `src/common/skeletal/opengpa_joint_names.py` | Create | Thin shim: `get_canonical_joint_names() -> List[str]` wraps `SkeletonRegistry.resolve("smplx")`. Single source of truth for the JS export. |
| `tests/unit/skeletal/test_opengpa_joint_names.py` | Create | Asserts the shim returns SMPLX joint names; cross-language schema test against the generated TS file. |
| `scripts/export_joint_names_ts.py` | Create | Build script: writes `workbench-ui/src/lib/jointNames.ts` from the Python list. |
| `workbench-ui/src/lib/jointNames.ts` | Generated (committed) | `export const JOINT_NAMES: readonly string[] = [...]` produced by the build script. |
| `workbench-ui/src/components/JointMarkers.tsx` | Create | R3F component that renders `<mesh name="joint_<smplx_name>" position={...}>` per joint. |
| `workbench-ui/src/lib/opengpaSidecar.ts` | Create | Wraps `@opengpa/threejs-sidecar` for use inside R3F (`useFrame` integration, capture toggle). |
| `workbench-ui/src/components/Viewer3D.tsx` | Modify (line 782 area) | Add `onCreated` to Canvas; mount `<JointMarkers>`; wire sidecar. |
| `workbench-ui/src/hooks/useOpenGPAToggle.ts` | Create | localStorage-backed toggle for OpenGPA capture (consistent with existing `usePersistedState` hook). |
| `workbench-ui/package.json` | Modify | Add `"@opengpa/threejs-sidecar": "file:../../gla/clients/threejs"` (local install during development). |
| `tests/e2e/test_workbench_browser.py` | Modify | New test: toggle OpenGPA on, generate motion, assert `/api/v1/frames/{N}/objects` returns the markers. |

---

## Tasks

### Task 1: Extract `clients/threejs/` from the Chrome extension subtree

**Repo:** `gla/`

**Files:**
- Create: `clients/threejs/index.js`
- Create: `clients/threejs/package.json`
- Create: `clients/threejs/README.md`
- Create: `clients/threejs/test.js`
- Modify: `src/shims/webgl/extension/bhdr-threejs-plugin.js`

- [ ] **Step 1: Write the failing smoke test**

Create `clients/threejs/test.js`:

```js
// Minimal smoke test — uses Node 18+ built-in test runner.
// Exercises the extracted client's POST behavior against an in-process stub.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import OpenGPAThreePlugin from './index.js';

test('capture() POSTs metadata to /api/v1/frames/{n}/metadata', async () => {
  const received = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      received.push({ url: req.url, body: JSON.parse(body) });
      res.end('{"status":"ok"}');
    });
  });
  await new Promise((r) => server.listen(0, r));
  const port = server.address().port;

  const fakeScene = { traverse: (cb) => cb({ name: 'root', type: 'Scene', isMesh: false }) };
  const fakeCamera = {};
  const plugin = new OpenGPAThreePlugin(null, `http://127.0.0.1:${port}`);
  plugin.capture(fakeScene, fakeCamera);

  // Wait one tick for the fetch to complete.
  await new Promise((r) => setTimeout(r, 50));
  server.close();

  assert.equal(received.length, 1);
  assert.match(received[0].url, /\/api\/v1\/frames\/0\/metadata$/);
  assert.equal(received[0].body.framework, 'threejs');
  assert.ok(Array.isArray(received[0].body.objects));
});
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd /home/jingyulee/gh/gla/clients/threejs && node --test test.js
```

Expected: FAIL — `Cannot find module './index.js'`.

- [ ] **Step 3: Move the existing plugin**

Copy `/home/jingyulee/gh/gla/src/shims/webgl/extension/bhdr-threejs-plugin.js` (120 LOC, already self-contained) to `clients/threejs/index.js`.

Replace the bottom export block with a clean ES default + named export:

```js
// At bottom of clients/threejs/index.js — replace existing module.exports/window blocks:
export default OpenGPAThreePlugin;
export { OpenGPAThreePlugin };

// Backwards compat for Chrome extension's <script>-tag injection:
if (typeof window !== 'undefined') {
  window.OpenGPAThreePlugin = OpenGPAThreePlugin;
}
```

- [ ] **Step 4: Add the package manifest**

Create `clients/threejs/package.json`:

```json
{
  "name": "@opengpa/threejs-sidecar",
  "version": "0.1.0",
  "description": "OpenGPA Tier-3 metadata sidecar for Three.js. POSTs scene-graph metadata to the OpenGPA engine for agent-driven debugging.",
  "type": "module",
  "main": "index.js",
  "exports": "./index.js",
  "files": ["index.js", "README.md"],
  "scripts": {
    "test": "node --test test.js"
  },
  "license": "MIT"
}
```

- [ ] **Step 5: Run the test, confirm it passes**

```bash
cd /home/jingyulee/gh/gla/clients/threejs && node --test test.js
```

Expected: PASS, 1 test.

- [ ] **Step 6: Decide back-compat shape, then update the extension's plugin file**

**Load-bearing check first** — the existing plugin uses `module.exports` and `window.OpenGPAThreePlugin`, which means the extension almost certainly loads it via `<script src=...>` (script-tag, not ES module). An `export` re-export would silently break the extension. Read `src/shims/webgl/extension/manifest.json` and `src/shims/webgl/extension/content.js` first to confirm the load mechanism.

- If `<script>`-tag loaded (most likely): replace `src/shims/webgl/extension/bhdr-threejs-plugin.js` with a **plain copy** of the canonical file's content (same source as `clients/threejs/index.js`, but with the original `module.exports` / `window` blocks at the bottom — not the ES `export`). Add a top-of-file comment: `// COPY of clients/threejs/index.js — kept here for the Chrome extension's <script>-tag loader. Edit clients/threejs/index.js, then re-copy.`
- If ES-module loaded: use the one-line re-export `export { default, OpenGPAThreePlugin } from '../../../clients/threejs/index.js';`.

This is the only step where getting the load mechanism wrong silently breaks the extension — verify before committing.

- [ ] **Step 7: Write the README**

Create `clients/threejs/README.md`:

```markdown
# @opengpa/threejs-sidecar

OpenGPA Tier-3 metadata sidecar for Three.js.

## Install

    npm install @opengpa/threejs-sidecar

## Use

```js
import OpenGPAThreePlugin from '@opengpa/threejs-sidecar';

const gpa = new OpenGPAThreePlugin(renderer, 'http://127.0.0.1:18080', 'YOUR_TOKEN');

// In your render loop, after renderer.render(scene, camera):
gpa.capture(scene, camera);
```

The sidecar walks the Three.js scene graph and POSTs framework metadata
(named objects, transforms, materials, lights, camera) to the OpenGPA
engine's `/api/v1/frames/{id}/metadata` endpoint. The engine exposes this
to agents via MCP tools (`query_object`, `list_objects`, `explain_pixel`).

If the engine is not running, POSTs fail silently — your app is unaffected.
\```
```

- [ ] **Step 8: Commit**

```bash
cd /home/jingyulee/gh/gla
git add clients/threejs/ src/shims/webgl/extension/bhdr-threejs-plugin.js
git commit -m "feat(clients): extract Three.js sidecar as @opengpa/threejs-sidecar"
```

---

### Task 2: Joint-name shim in omnispace-gen (Python source of truth)

**Repo:** `omnispace-gen/`

**Files:**
- Create: `src/common/skeletal/opengpa_joint_names.py`
- Create: `tests/unit/skeletal/test_opengpa_joint_names.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/skeletal/test_opengpa_joint_names.py`:

```python
"""Test the canonical joint-name list exposed for OpenGPA Tier-3 markers."""
from common.skeletal.opengpa_joint_names import get_canonical_joint_names


def test_returns_smplx_joint_names():
    names = get_canonical_joint_names()
    assert isinstance(names, list)
    # SMPLX has 55 joints; pelvis is canonically the root.
    assert len(names) >= 22
    assert names[0] == "pelvis"
    # Spot-check a few standard SMPLX joints:
    for required in ("left_shoulder", "right_shoulder", "left_knee", "right_knee"):
        assert required in names, f"missing {required}"


def test_is_stable_across_calls():
    # Implementation may cache the SkeletonRegistry result; ensure repeated
    # calls return identical content (same order, same names).
    a = get_canonical_joint_names()
    b = get_canonical_joint_names()
    assert a == b
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
cd /home/jingyulee/gh/omnispace-gen && PYTHONPATH=src pytest tests/unit/skeletal/test_opengpa_joint_names.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'common.skeletal.opengpa_joint_names'`.

- [ ] **Step 3: Implement the shim**

Create `src/common/skeletal/opengpa_joint_names.py`:

```python
"""Canonical joint-name list for OpenGPA Tier-3 markers.

This is the single source of truth consumed by both the Python sidecar (Open3D
renderer, Phase 2) and the workbench TypeScript layer (Phase 1, via the
generated workbench-ui/src/lib/jointNames.ts file).

Naming is delegated to the SMPLX skeleton config in configs/skeletons/smplx.yaml
to keep skeleton ownership in one place. If you change the SMPLX joint set, the
generated TS file must be regenerated via scripts/export_joint_names_ts.py.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from common.skeletal.registry import SkeletonRegistry


@lru_cache(maxsize=1)
def get_canonical_joint_names() -> List[str]:
    """Return the SMPLX joint names in their canonical (skeleton-config) order."""
    smplx = SkeletonRegistry.resolve("smplx")
    return list(smplx.joint_names)
```

- [ ] **Step 4: Run test, confirm pass**

```bash
cd /home/jingyulee/gh/omnispace-gen && PYTHONPATH=src pytest tests/unit/skeletal/test_opengpa_joint_names.py -v
```

Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
cd /home/jingyulee/gh/omnispace-gen
git add src/common/skeletal/opengpa_joint_names.py tests/unit/skeletal/test_opengpa_joint_names.py
git commit -m "feat(skeletal): add OpenGPA canonical joint-name shim over SkeletonRegistry"
```

---

### Task 3: Generate `workbench-ui/src/lib/jointNames.ts` + cross-language schema test

**Repo:** `omnispace-gen/`

**Files:**
- Create: `scripts/export_joint_names_ts.py`
- Create (generated, committed): `workbench-ui/src/lib/jointNames.ts`
- Modify: `tests/unit/skeletal/test_opengpa_joint_names.py` (add cross-language assertion)

- [ ] **Step 1: Write the failing cross-language test**

Append to `tests/unit/skeletal/test_opengpa_joint_names.py`:

```python
import re
from pathlib import Path

from common.skeletal.opengpa_joint_names import get_canonical_joint_names


def test_ts_export_matches_python_source():
    """The generated TS file MUST match the Python source — drift is a bug."""
    repo_root = Path(__file__).resolve().parents[3]
    ts_file = repo_root / "workbench-ui" / "src" / "lib" / "jointNames.ts"
    assert ts_file.exists(), (
        f"{ts_file} missing. Regenerate via "
        f"`python scripts/export_joint_names_ts.py`."
    )
    content = ts_file.read_text()
    # Extract the array literal: export const JOINT_NAMES = [ "a", "b", ... ];
    match = re.search(r"JOINT_NAMES[^=]*=\s*\[(.*?)\]", content, re.DOTALL)
    assert match, f"Could not parse JOINT_NAMES array in {ts_file}"
    ts_names = re.findall(r'"([^"]+)"', match.group(1))
    py_names = get_canonical_joint_names()
    assert ts_names == py_names, (
        f"TS export drifted from Python source. "
        f"Regenerate via `python scripts/export_joint_names_ts.py`. "
        f"Python: {py_names!r}\nTS: {ts_names!r}"
    )
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
cd /home/jingyulee/gh/omnispace-gen && PYTHONPATH=src pytest tests/unit/skeletal/test_opengpa_joint_names.py::test_ts_export_matches_python_source -v
```

Expected: FAIL — TS file missing.

- [ ] **Step 3: Implement the export script**

Create `scripts/export_joint_names_ts.py`:

```python
#!/usr/bin/env python
"""Generate workbench-ui/src/lib/jointNames.ts from the Python source of truth.

Run after changing the SMPLX skeleton config or the joint-name shim.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from common.skeletal.opengpa_joint_names import get_canonical_joint_names


HEADER = """// AUTO-GENERATED — DO NOT EDIT BY HAND.
// Regenerate via: python scripts/export_joint_names_ts.py
// Source of truth: src/common/skeletal/opengpa_joint_names.py
"""


def main() -> int:
    names = get_canonical_joint_names()
    body = "export const JOINT_NAMES: readonly string[] = [\n"
    for name in names:
        body += f'  "{name}",\n'
    body += "] as const;\n"
    out = REPO_ROOT / "workbench-ui" / "src" / "lib" / "jointNames.ts"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEADER + "\n" + body)
    print(f"Wrote {out} ({len(names)} joints)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the export script**

```bash
cd /home/jingyulee/gh/omnispace-gen && python scripts/export_joint_names_ts.py
```

Expected: prints `Wrote …/jointNames.ts (N joints)`.

- [ ] **Step 5: Run the test, confirm it passes**

```bash
cd /home/jingyulee/gh/omnispace-gen && PYTHONPATH=src pytest tests/unit/skeletal/test_opengpa_joint_names.py -v
```

Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
cd /home/jingyulee/gh/omnispace-gen
git add scripts/export_joint_names_ts.py workbench-ui/src/lib/jointNames.ts \
        tests/unit/skeletal/test_opengpa_joint_names.py
git commit -m "feat(workbench): export canonical joint names to TS for OpenGPA markers"
```

---

### Task 4: `JointMarkers` R3F component

**Repo:** `omnispace-gen/`

**Files:**
- Create: `workbench-ui/src/components/JointMarkers.tsx`

This component renders one named mesh per joint at the joint's world position — the named meshes are what the OpenGPA sidecar serializes into the metadata POST.

- [ ] **Step 1: Implement the component**

Create `workbench-ui/src/components/JointMarkers.tsx`:

```tsx
import { useMemo } from "react";
import * as THREE from "three";
import type { MotionData } from "../types/motion";
import { JOINT_NAMES } from "../lib/jointNames";

interface Props {
  motion: MotionData;
  frame: number;
  /** Marker radius in world units. */
  radius?: number;
  /** Visibility — markers are always part of the scene graph for OpenGPA, but
      can be made invisible to the user. The OpenGPA sidecar serializes them
      regardless of `visible` (the Three.js plugin sets `visible: obj.visible`). */
  visible?: boolean;
}

/**
 * Renders one named THREE.Mesh per SMPLX joint at the joint's world position.
 * Each mesh has `name = "joint_<smplx_name>"`. The OpenGPA Three.js sidecar
 * picks these up automatically and POSTs them as Tier-3 metadata.
 *
 * Joints beyond `motion.shape[1]` are skipped (compact skeletons like
 * HumanML3D-22 only use a prefix of the SMPLX list).
 */
export function JointMarkers({ motion, frame, radius = 0.025, visible = true }: Props) {
  const positions = useMemo(() => {
    const J = motion?.shape?.[1] ?? 0;
    const T = motion?.shape?.[0] ?? 0;
    if (J === 0 || T === 0 || !motion?.positions) return [];
    const f = Math.max(0, Math.min(frame, T - 1));
    const out: [number, number, number][] = [];
    for (let j = 0; j < Math.min(J, JOINT_NAMES.length); j++) {
      const idx = (f * J + j) * 3;
      out.push([
        motion.positions[idx],
        motion.positions[idx + 1],
        motion.positions[idx + 2],
      ]);
    }
    return out;
  }, [motion, frame]);

  return (
    <group name="opengpa_joint_markers">
      {positions.map((p, j) => (
        <mesh
          key={j}
          name={`joint_${JOINT_NAMES[j]}`}
          position={p}
          visible={visible}
        >
          <sphereGeometry args={[radius, 8, 8]} />
          <meshBasicMaterial color="#ff00ff" />
        </mesh>
      ))}
    </group>
  );
}
```

- [ ] **Step 2: Type-check the component**

```bash
cd /home/jingyulee/gh/omnispace-gen/workbench-ui && npx tsc --noEmit
```

Expected: No errors related to `JointMarkers.tsx`. Pre-existing errors in other files are acceptable; only `JointMarkers.tsx`-related diagnostics are blockers for this task.

- [ ] **Step 3: Commit**

```bash
cd /home/jingyulee/gh/omnispace-gen
git add workbench-ui/src/components/JointMarkers.tsx
git commit -m "feat(workbench): add JointMarkers R3F component for OpenGPA Tier-3"
```

---

### Task 5: OpenGPA sidecar wrapper + npm install

**Repo:** `omnispace-gen/`

**Files:**
- Modify: `workbench-ui/package.json`
- Create: `workbench-ui/src/lib/opengpaSidecar.ts`
- Create: `workbench-ui/src/hooks/useOpenGPAToggle.ts`

- [ ] **Step 1: Add the local file dependency**

Edit `workbench-ui/package.json` to add to `dependencies`:

```json
"@opengpa/threejs-sidecar": "file:../../gla/clients/threejs"
```

(Adjust the relative path if your `gla/` sibling layout differs — verify with `ls ../../gla/clients/threejs` from `workbench-ui/`.)

- [ ] **Step 2: Install**

```bash
cd /home/jingyulee/gh/omnispace-gen/workbench-ui && npm install
```

Expected: installs `@opengpa/threejs-sidecar@0.1.0` from the local path. Verify:

```bash
node -e "import('@opengpa/threejs-sidecar').then(m => console.log(typeof m.default))"
```

Expected: prints `function`.

- [ ] **Step 3: Implement the toggle hook**

Create `workbench-ui/src/hooks/useOpenGPAToggle.ts`:

```ts
import { usePersistedState } from "./usePersistedState";

const STORAGE_KEY = "opengpa.captureEnabled";

/**
 * Returns the OpenGPA capture toggle state, persisted in localStorage.
 * When OFF, the sidecar is not instantiated and no metadata POSTs happen.
 */
export function useOpenGPAToggle(): [boolean, (v: boolean) => void] {
  return usePersistedState<boolean>(STORAGE_KEY, false);
}
```

If `usePersistedState`'s exact signature differs, adapt to match — the file already exists at `workbench-ui/src/hooks/usePersistedState.ts`, read it before this step.

- [ ] **Step 4: Implement the sidecar wrapper**

Create `workbench-ui/src/lib/opengpaSidecar.ts`:

```ts
import OpenGPAThreePlugin from "@opengpa/threejs-sidecar";
import type * as THREE from "three";

const ENGINE_URL = "http://127.0.0.1:18080";
// Token is dev-only for now; later read from configs/paths.yaml via the
// workbench server's /api/config endpoint if/when auth is enforced.
const TOKEN = "";

/**
 * Thin wrapper that owns one OpenGPAThreePlugin instance per renderer.
 * Call captureFrame(scene, camera) from a useFrame() hook in the Canvas.
 *
 * Lifecycle: instantiated lazily on first captureFrame() call. To disable,
 * gate the call site on the OpenGPA toggle (useOpenGPAToggle) — this
 * module does not consult the toggle directly to keep the lib pure.
 */
export class OpenGPASidecar {
  private plugin: OpenGPAThreePlugin | null = null;

  attach(renderer: THREE.WebGLRenderer): void {
    if (this.plugin) return;
    this.plugin = new OpenGPAThreePlugin(renderer, ENGINE_URL, TOKEN);
  }

  captureFrame(scene: THREE.Scene, camera: THREE.Camera): void {
    if (!this.plugin) return;
    this.plugin.capture(scene, camera);
  }
}
```

- [ ] **Step 5: Type-check**

```bash
cd /home/jingyulee/gh/omnispace-gen/workbench-ui && npx tsc --noEmit
```

Expected: no new errors related to the new files. If `@opengpa/threejs-sidecar` lacks types, add `workbench-ui/src/lib/opengpaSidecar.d.ts`:

```ts
declare module "@opengpa/threejs-sidecar" {
  export default class OpenGPAThreePlugin {
    constructor(renderer: unknown, url?: string, token?: string);
    capture(scene: unknown, camera: unknown): void;
  }
}
```

- [ ] **Step 6: Commit**

```bash
cd /home/jingyulee/gh/omnispace-gen
git add workbench-ui/package.json workbench-ui/package-lock.json \
        workbench-ui/src/lib/opengpaSidecar.ts \
        workbench-ui/src/hooks/useOpenGPAToggle.ts
# Plus the .d.ts shim if it was needed:
git add workbench-ui/src/lib/opengpaSidecar.d.ts 2>/dev/null || true
git commit -m "feat(workbench): wrap @opengpa/threejs-sidecar with capture toggle hook"
```

---

### Task 6: Mount JointMarkers + sidecar in `Viewer3D.tsx`; expose toggle in UI

**Repo:** `omnispace-gen/`

**Files:**
- Modify: `workbench-ui/src/components/Viewer3D.tsx`

This is the load-bearing wiring step. After this task, the workbench actually emits Tier-3 metadata when the toggle is on.

- [ ] **Step 1: Read the current Canvas setup**

Open `workbench-ui/src/components/Viewer3D.tsx`. Find the `<Canvas …>` element near line 782 (and its closing tag near line 939). Identify (a) where you have access to `motion` and the current `frame`, (b) which child components currently render inside Canvas. Note the existing pattern — this codebase's conventions take priority over generic R3F advice.

- [ ] **Step 2: Add the toggle UI control**

Locate the toolbar / debug panel area in `Viewer3D.tsx` (the existing `RenderModeSelector` or similar control row is the right neighbor). Add an inline checkbox:

```tsx
import { useOpenGPAToggle } from "../hooks/useOpenGPAToggle";
// ... inside the toolbar JSX:
const [openGPACapture, setOpenGPACapture] = useOpenGPAToggle();
// ...
<label style={{ marginLeft: 12, fontSize: 12 }}>
  <input
    type="checkbox"
    checked={openGPACapture}
    onChange={(e) => setOpenGPACapture(e.target.checked)}
  />{" "}
  OpenGPA capture
</label>
```

- [ ] **Step 3: Wire the sidecar inside Canvas**

Inside the existing `<Canvas …>` (around line 782), use `onCreated` to attach the sidecar to the renderer, then add an inner R3F component that calls `captureFrame` from `useFrame`:

```tsx
import { useFrame } from "@react-three/fiber";
import { OpenGPASidecar } from "../lib/opengpaSidecar";
import { JointMarkers } from "./JointMarkers";

// At top of Viewer3D component body (near other useMemo / useState):
const sidecarRef = useRef(new OpenGPASidecar());

// ... inside <Canvas>, BEFORE the closing tag:
<Canvas
  camera={{ position: [3, 2, 3], fov: 50 }}
  onCreated={({ gl }) => {
    if (openGPACapture) sidecarRef.current.attach(gl);
  }}
>
  {/* existing children */}
  {openGPACapture && motion ? (
    <>
      <JointMarkers motion={motion} frame={currentFrame} visible={false} />
      <OpenGPACaptureLoop sidecar={sidecarRef.current} enabled={openGPACapture} />
    </>
  ) : null}
</Canvas>
```

Define `OpenGPACaptureLoop` next to the Viewer3D component (or in `opengpaSidecar.ts` if you prefer):

```tsx
function OpenGPACaptureLoop({
  sidecar,
  enabled,
}: {
  sidecar: OpenGPASidecar;
  enabled: boolean;
}) {
  useFrame(({ scene, camera, gl }) => {
    if (!enabled) return;
    sidecar.attach(gl); // idempotent
    sidecar.captureFrame(scene, camera);
  });
  return null;
}
```

`visible={false}` on `<JointMarkers>` keeps the markers as scene-graph nodes (so the sidecar serializes them) without cluttering the user-facing render. Flip to `visible={true}` if you want to see them while debugging.

- [ ] **Step 4: Identify `currentFrame`'s actual variable name**

Step 3 references `currentFrame` and `motion`. Inspect Viewer3D's existing JSX (the `SkeletonRenderer` / `BodyRenderer` props) to find what these are actually called in this component, and substitute. Do not invent variable names.

- [ ] **Step 5: Type-check + lint**

```bash
cd /home/jingyulee/gh/omnispace-gen/workbench-ui && npx tsc --noEmit && npm run lint
```

Expected: no new errors related to the modifications.

- [ ] **Step 6: Manual smoke check**

```bash
# Terminal 1 — start OpenGPA engine (from gla repo, see gla/CLAUDE.md):
cd /home/jingyulee/gh/gla
PY311=$(bazel info output_base)/external/rules_python~~python~python_3_11_x86_64-unknown-linux-gnu/bin/python3.11
PYTHONPATH="src/python:bazel-bin/src/bindings" $PY311 -m gpa.launcher \
    --socket /tmp/gpa.sock --shm /gpa --port 18080 --token ""

# Terminal 2 — start workbench in mock mode (no GPU needed):
cd /home/jingyulee/gh/omnispace-gen
motiongen workbench --port 8420 --mock

# Browser:
# 1. Open http://localhost:8420
# 2. Click "OpenGPA capture" checkbox
# 3. Generate a motion (any text prompt)

# Terminal 3 — verify metadata reached the engine:
curl -s http://127.0.0.1:18080/api/v1/frames/0/metadata | python -m json.tool
```

Expected: JSON response with `framework: "threejs"`, non-zero `object_count`. The `joint_*` markers will be among the objects (verify in next task with a specific endpoint).

- [ ] **Step 7: Commit**

```bash
cd /home/jingyulee/gh/omnispace-gen
git add workbench-ui/src/components/Viewer3D.tsx
git commit -m "feat(workbench): wire OpenGPA sidecar + JointMarkers into Viewer3D"
```

---

### Task 7: E2E test — toggle on, generate motion, assert markers reach the engine

**Repo:** `omnispace-gen/`

**Files:**
- Modify: `tests/e2e/test_workbench_browser.py`

- [ ] **Step 1: Write the failing E2E test**

Append (or open the existing browser-test fixture) and add:

```python
import json
import time
import urllib.request

import pytest


@pytest.mark.e2e
def test_opengpa_sidecar_emits_joint_markers(workbench_page, bhdr_engine):
    """With OpenGPA capture toggled on, generated motion produces metadata
    POSTs containing all canonical joint markers."""
    # bhdr_engine fixture: starts gla engine on :18080, yields its base URL.
    # workbench_page fixture: launches workbench in mock mode + Playwright page.

    page = workbench_page

    # Toggle OpenGPA capture on.
    page.get_by_label("OpenGPA capture").check()

    # Generate any motion (mock backend produces fixed output).
    page.get_by_role("button", name="Generate").click()

    # Wait for the workbench to render a few frames.
    time.sleep(2.0)

    # Query the engine for the most recent metadata POST.
    base = bhdr_engine.rstrip("/")
    # Frames are numbered from 0 in workbench mode (sidecar's local counter).
    # Try the first few frame IDs and pick the highest one with metadata.
    for frame_id in range(20, -1, -1):
        try:
            with urllib.request.urlopen(f"{base}/api/v1/frames/{frame_id}/objects") as r:
                payload = json.loads(r.read())
                break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
    else:
        pytest.fail("No metadata reached the engine after toggling capture on.")

    object_names = {obj["name"] for obj in payload["objects"]}

    # Load the canonical joint list from the same Python source the workbench
    # consumes via the generated TS — they MUST agree by construction.
    from common.skeletal.opengpa_joint_names import get_canonical_joint_names

    expected = {f"joint_{n}" for n in get_canonical_joint_names()[:22]}  # body subset
    missing = expected - object_names
    assert not missing, (
        f"Workbench Tier-3 metadata missing joint markers: {sorted(missing)[:5]}"
    )
```

If the `bhdr_engine` fixture does not yet exist in the test conftest, add it. It should `subprocess.Popen` the gla engine (per `gla/CLAUDE.md` "Running the Eval" section), wait for `:18080` to accept connections, yield the URL, then terminate cleanly.

The engine launcher requires Bazel-built artifacts (`bazel-bin/src/bindings`). The fixture should skip the test (not fail it) if the build artifacts are missing — use `pytest.importorskip` or check `Path(...).exists()` and `pytest.skip("Run `bazel build //...` first.")`. CI environments without Bazel should not block this test from being committed.

- [ ] **Step 2: Run the test, expect it to pass**

```bash
cd /home/jingyulee/gh/omnispace-gen && pytest tests/e2e/test_workbench_browser.py::test_opengpa_sidecar_emits_joint_markers -v
```

If it fails, check the order of operations:
1. Engine listening before workbench starts.
2. `OpenGPACaptureLoop` actually mounted (Step 3 of Task 6 — verify the conditional).
3. Frame IDs match — sidecar uses local counter; engine sees `frame_id=0`, `1`, `2`, ...

- [ ] **Step 3: Commit**

```bash
cd /home/jingyulee/gh/omnispace-gen
git add tests/e2e/test_workbench_browser.py
# Plus conftest changes if you added the bhdr_engine fixture:
git add tests/e2e/conftest.py 2>/dev/null || true
git commit -m "test(workbench): E2E asserts OpenGPA Tier-3 captures joint markers"
```

---

### Task 8: MCP smoke check — agent-style query against running stack

**Repo:** Either (verification, not new code).

**Files:** None — this task is purely a manual verification with documented output.

- [ ] **Step 1: With the stack running (engine + workbench from Task 6 Step 6), query a specific joint**

```bash
curl -s "http://127.0.0.1:18080/api/v1/frames/0/objects/joint_pelvis" | python -m json.tool
```

Expected: JSON with at least `name`, `transform.position` (3-element array). Note the position values.

- [ ] **Step 2: Confirm the position matches the underlying motion data**

In a Python REPL (workbench server side):

```python
from common.skeletal.opengpa_joint_names import get_canonical_joint_names
# Get the live workbench's most recent MotionSequence — exact accessor depends
# on how the mock generator exposes its output. The point is: position from the
# curl above MUST match motion.positions[0, pelvis_idx, :] within rounding.
```

If they match: Phase 1 plumbing works end-to-end. The agent can now ask "is joint X at the expected place" via standard MCP tools.

If they don't match: investigate the most likely culprit — Three.js coordinate frame (Y-up by default in r3f) vs MotionSequence's coordinate frame (per `omnispace-gen/CLAUDE.md`: "Y-up or Z-up; auto-converted by `TransformRegistry`"). The OpenGPA payload reports world-space positions in whatever frame `position.toArray()` returns at capture time — if there's an outer `<group rotation=...>` reorienting the scene, the markers' world positions will reflect that reorientation. This is correct behavior for Phase 1; document the convention rather than "fix" it.

- [ ] **Step 3: Document the result in the spec's "Open questions" section**

Open `docs/superpowers/specs/2026-04-28-omnispace-gen-integration-design.md`. The "Open questions" section currently reads "None at design time." — replace that line (or add below it under a new "Phase 1 findings" subhead) with a short note recording:
- What coordinate frame the workbench renders in (Y-up vs Z-up).
- Whether the captured marker positions match `MotionSequence.joints` directly or require a fixed transform.
- This is information Phase 2 (Open3D) will need to match.

```bash
cd /home/jingyulee/gh/gla
git add docs/superpowers/specs/2026-04-28-omnispace-gen-integration-design.md
git commit -m "docs(spec): record workbench coordinate-frame finding from Phase 1 smoke"
```

---

## End-of-plan checklist

After all tasks land:
- [ ] `gla/clients/threejs/` is a published-shape package; old extension path still works (back-compat re-export).
- [ ] `omnispace-gen/src/common/skeletal/opengpa_joint_names.py` exists and is consumed by both Python tests and the TS export script.
- [ ] `workbench-ui/src/lib/jointNames.ts` is committed; cross-language test catches drift.
- [ ] Workbench has a visible "OpenGPA capture" toggle, persisted in localStorage.
- [ ] With the toggle on and engine running, `curl :18080/api/v1/frames/{N}/objects/joint_pelvis` returns a valid transform.
- [ ] E2E test `test_opengpa_sidecar_emits_joint_markers` passes against the workbench in mock mode.
- [ ] Spec's Open questions section records the coordinate-frame result for Phase 2 to consume.

## Follow-ups (Plan B — Phase 2)

Plan B will cover, once Phase 1 is shipped:
- Extract `gla/clients/python/opengpa_client/` (Tier3Sidecar ABC, HTTP helper).
- Add joint markers to omnispace-gen's Open3D renderer (`src/motiongen/visualization/joint_markers.py`).
- Implement Open3D `Tier3Sidecar` subclass (`src/motiongen/visualization/opengpa_sidecar.py`).
- Add `tests/eval/r37_joint_offset_smplx/` agent-loop eval scenario in `gla/`.
- Resolve the Phase 2 frame-ID race (per spec note); decide whether to pin frame IDs via the engine's swap callback or accept the offset.
