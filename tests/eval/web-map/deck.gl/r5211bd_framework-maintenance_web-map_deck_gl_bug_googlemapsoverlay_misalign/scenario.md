## User Report

### Description

GoogleMapsOverlay shows data in wrong position in initial render when rendering on top of raster basemap.

actual:
<img width="664" alt="image" src="https://github.com/visgl/deck.gl/assets/1507542/a2ea591d-6121-4dea-8961-38a0e8389422">

(note screenshots and sample below on "free" google quota, same applies with proper, paid key)

### Flavors

- [ ] Script tag
- [ ] React
- [ ] Python/Jupyter notebook
- [ ] MapboxOverlay
- [X] GoogleMapsOverlay
- [ ] CartoLayer
- [ ] ArcGIS

### Expected Behavior

data: one "geo" rectantgle polygon with bounds more or less fitting mainland USA

expected:
<img width="667" alt="image" src="https://github.com/visgl/deck.gl/assets/1507542/03e7e38b-c4fd-44b6-bf1b-10b757c2bc08">

### Steps to Reproduce

Repro code (https://stackblitz.com/edit/vitejs-vite-prbtax?file=main.js,package.json,index.html&terminal=dev):
```
import { GoogleMapsOverlay } from '@deck.gl/google-maps';
import { Loader } from '@googlemaps/js-api-loader';
import { PolygonLayer } from '@deck.gl/layers';
(...)
  const loader = new Loader({ apiKey: GOOGLE_MAPS_API_KEY });
  const googlemaps = await loader.importLibrary('maps');

  const map = new googlemaps.Map(document.getElementById('map'), {
    mapTypeId: 'satellite',
    center: {
      lat: 43.291517478783575,
      lng: -88.24979240793371,
    },
    zoom: 3,
    tilt: 0,
    bearing: 0,
    disableDefaultUI: true,
  });

  const layers = [new PolygonLayer({
    id: 'PolygonLayer',
    data: [
      {
        id: 1,
        contour: [
          [-133.25358036092166, 49.255563717225385],
          [-133.25358036092166, 24.670835144274477],
          [-64.13509283629588, 24.670835144274477],
          [-64.13509283629588, 49.255563717225385],
          [-133.25358036092166, 49.255563717225385],
        ],
      },
    ],

    getPolygon: (d) => d.contour,
    getFillColor: (d) => [255, 0, 0, 125],
  })];
  const overlay = new GoogleMapsOverlay({ layers});
  overlay.setMap(map);
```

```

### Environment

- Framework version: 9.0.14
- Browser: Chrome
- OS: MacOS

### Logs

_No response_

Closes #8892 (https://github.com/visgl/deck.gl/pull/8892)

## Expected

Behavior

data: one "geo" rectantgle polygon with bounds more or less fitting mainland USA

expected:
<img width="667" alt="image" src="https://github.com/visgl/deck.gl/assets/1507542/03e7e38b-c4fd-44b6-bf1b-10b757c2bc08">

## Actual

GoogleMapsOverlay shows data in wrong position in initial render when rendering on top of raster basemap.

actual:
<img width="664" alt="image" src="https://github.com/visgl/deck.gl/assets/1507542/a2ea591d-6121-4dea-8961-38a0e8389422">

(note screenshots and sample below on "free" google quota, same applies with proper, paid key)

## Ground Truth

See fix at https://github.com/visgl/deck.gl/pull/8892.

## Fix

```yaml
fix_pr_url: https://github.com/visgl/deck.gl/pull/8892
fix_sha: d504327e80ac9f83ecf1db094c9975c553cf2c6b
fix_parent_sha: b5a631371354757254b2fd16c6524ee258eb091e
bug_class: consumer-misuse
files:
  - modules/google-maps/src/google-maps-overlay.ts
```
