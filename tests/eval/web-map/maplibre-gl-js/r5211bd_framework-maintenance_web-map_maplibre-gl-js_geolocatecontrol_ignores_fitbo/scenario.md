## User Report

**maplibre-gl-js version**: 5.21.1

**browser**: Chrome / Safari

### Steps to Trigger Behavior

1. Create a map and set the projection to `vertical-perspective`.
2. Add a `GeolocateControl` with `trackUserLocation: true` and `fitBoundsOptions: { maxZoom: 15 }`.
3. Click the geolocate button when the map is in `vertical-perspective`.

### Link to Demonstration

Paste this into https://jsbin.com.
```html
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>MapLibre vertical-perspective geolocate repro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link
      rel="stylesheet"
      href="https://unpkg.com/maplibre-gl@5.21.1/dist/maplibre-gl.css"
    />
    <style>
      html, body, #map {
        margin: 0;
        width: 100%;
        height: 100%;
      }

      .panel {
        position: absolute;
        top: 12px;
        left: 12px;
        z-index: 2;
        background: rgba(255, 255, 255, 0.96);
        padding: 10px 12px;
        border-radius: 8px;
        font: 12px/1.4 sans-serif;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.18);
        max-width: 360px;
      }

      .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }

      button {
        margin-right: 8px;
        margin-top: 6px;
      }
    </style>
  </head>
  <body>
    <div class="panel">
      <div><strong>Repro:</strong> GeolocateControl + vertical-perspective</div>
      <div>Projection: <span id="projection" class="mono">vertical-perspective</span></div>
      <div>Zoom: <span id="zoom" class="mono">7.00</span></div>
      <div>Geolocate max zoom: <span class="mono">14</span></div>
      <div style="margin-top:8px">
        1. Open this in full JSBin output mode over HTTPS.<br />
        2. Allow location access for the page.<br />
        3. Leave projection on <span class="mono">vertical-perspective</span>.<br />
        4. Click the native geolocate button.<br />
        5. Compare with <span class="mono">mercator</span>.
      </div>
      <div style="margin-top:8px">
        Expected: geolocate should not zoom above 14.<br />
        Actual: in <span class="mono">vertical-perspective</span>, it can still zoom beyond the configured limit.
      </div>
      <div style="margin-top:8px">
        <button id="vertical">vertical-perspective</button>
        <button id="mercator">mercator</button>
      </div>
    </div>

    <div id="map"></div>

    <script src="https://unpkg.com/maplibre-gl@5.21.1/dist/maplibre-gl.js"></script>
    <script>
      const GEOLOCATE_CONTROL_MAX_ZOOM = 14;

      const projectionLabel = document.getElementById('projection');
      const zoomLabel = document.getElementById('zoom');

      const map = new maplibregl.Map({
        container: 'map',
        style: 'https://demotiles.maplibre.org/style.json',
        center: [4.9, 52.37],
        zoom: 7
      });

      const geolocate = new maplibregl.GeolocateControl({
        positionOptions: {
          enableHighAccuracy: true
        },
        fitBoundsOptions: {
          maxZoom: GEOLOCATE_CONTROL_MAX_ZOOM
        },
        trackUserLocation: true,
        showUserLocation: true,
        showAccuracyCircle: true
      });

      map.addControl(new maplibregl.NavigationControl(), 'top-right');
      map.addControl(geolocate, 'top-right');

      function applyProjection(type) {
        map.setProjection({ type });
        projectionLabel.textContent = type;
        console.log('projection', type, 'zoom', map.getZoom());
      }

      map.on('load', () => {
        applyProjection('vertical-perspective');
        zoomLabel.textContent = map.getZoom().toFixed(2);
      });

      map.on('zoom', () => {
        zoomLabel.textContent = map.getZoom().toFixed(2);
      });

      document.getElementById('vertical').addEventListener('click', () => {
        applyProjection('vertical-perspective');
      });

      document.getElementById('mercator').addEventListener('click', () => {
        applyProjection('mercator');
      });

      geolocate.on('geolocate', (event) => {
        console.log('geolocate', {
          accuracy: event.coords.accuracy,
          zoom: map.getZoom(),
          projection: projectionLabel.textContent
        });
      });

      map.on('moveend', (event) => {
        console.log('moveend', {
          zoom: map.getZoom(),
          projection: projectionLabel.textContent,
          geolocateSource: !!(event && event.geolocateSource)
        });
      });
    </script>
  </body>
</html>
```

### Expected Behavior

`GeolocateControl` should respect `fitBoundsOptions.maxZoom` consistently.
With `fitBoundsOptions: { maxZoom: 15 }`, the map should not zoom past level 15 during geolocation, regardless of projection.

### Actual Behavior

When the map projection is `mercator`, geolocation respects the zoom cap as expected.

When the map projection is `vertical-perspective`, the first geolocate action can zoom past `maxZoom: 15` (for example to zoom 18), as if the cap is ignored.

Related symptom:
if the map is allowed to zoom beyond the source/style max zoom while using `vertical-perspective`, the map can render incorrectly or turn black.

Notes:
- The issue appears tied to `vertical-perspective`, not the geolocate button wiring in app code.
- `GeolocateControl` uses `fitBounds` internally for camera updates, so this looks like a projection-specific bug/limitation in geolocate camera handling.
- In the same setup, replacing `vertical-perspective` with `mercator` makes the problem go away.

Closes #7372 (https://github.com/maplibre/maplibre-gl-js/pull/7372)

## Expected

Behavior

`GeolocateControl` should respect `fitBoundsOptions.maxZoom` consistently.
With `fitBoundsOptions: { maxZoom: 15 }`, the map should not zoom past level 15 during geolocation, regardless of projection.

## Actual

Behavior

When the map projection is `mercator`, geolocation respects the zoom cap as expected.

When the map projection is `vertical-perspective`, the first geolocate action can zoom past `maxZoom: 15` (for example to zoom 18), as if the cap is ignored.

Related symptom:
if the map is allowed to zoom beyond the source/style max zoom while using `vertical-perspective`, the map can render incorrectly or turn black.

Notes:
- The issue appears tied to `vertical-perspective`, not the geolocate button wiring in app code.
- `GeolocateControl` uses `fitBounds` internally for camera updates, so this looks like a projection-specific bug/limitation in geolocate camera handling.
- In the same setup, replacing `vertical-perspective` with `mercator` makes the problem go away.

Closes #7372 (https://github.com/maplibre/maplibre-gl-js/pull/7372)

## Ground Truth

See fix at https://github.com/maplibre/maplibre-gl-js/pull/7372.

## Fix

```yaml
fix_pr_url: https://github.com/maplibre/maplibre-gl-js/pull/7372
fix_sha: 6de93359410aae6f32654f8b3521206147d2fd71
bug_class: consumer-misuse
files:
  - src/geo/projection/vertical_perspective_camera_helper.ts
```
