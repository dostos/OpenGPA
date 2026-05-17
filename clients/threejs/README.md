# @opengpa/threejs-sidecar

Beholder Tier-3 metadata sidecar for Three.js.

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
(named objects, transforms, materials, lights, camera) to the Beholder
engine's `/api/v1/frames/{id}/metadata` endpoint. The engine exposes this
to agents via MCP tools (`query_object`, `list_objects`, `explain_pixel`).

If the engine is not running, POSTs fail silently — your app is unaffected.
