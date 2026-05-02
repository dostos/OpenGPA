## User Report

**Description**
Starting with MapLibre GL JS version 5.0.0, I can see visually intersecting “stripes” when rendering a 3D terrain scene with semi‐transparent forest polygons from custom .pbf vector tiles. These stripes look more opaque or darker where polygons overlap, creating a crossed “banding” pattern. Reverting to version 4.7.1 eliminates the issue.

![Image](https://github.com/user-attachments/assets/f702676a-137b-4306-8049-cd37a334ff6d)

**Steps to Reproduce**

1. Use a custom 3D terrain source (RGB tiles in .png format).
2. Use a custom raster background (tiles in .jpg format) – not necessary to reproduce bug.
3. Add a custom vector landcover layer (forest) with partial transparency on the fill. For example:
```
map.addLayer({
        'id': 'forests',
        'type': 'fill',
        'source-layer': 'landcover',
        'source': 'vector',
        'minzoom': 11,
        'filter': ['==', ['get', 'type'], 'forest'],
        "paint": {
            'fill-color': '#076b1b',
            'fill-opacity': 0.2
        }
    });
```

4. Tilt/rotate the map in 3D mode.
5. Observe crossing stripes or darker bands where the partially transparent polygons overlap.

https://jsfiddle.net/stempek/o8v92qpt/22/

**Expected Behavior**
![Image](https://github.com/user-attachments/assets/2dbdc455-a1cb-4848-8c71-9d348b4fe275)

A smooth, semi‐transparent rendering of the forest polygons in 3D, without any noticeable intersecting stripes (version 4.7.1).

**Actual Behavior**

![Image](https://github.com/user-attachments/assets/1625eff5-21f1-4bbc-b61b-82805e1ee46b)

Distinct intersecting stripes of darker or more opaque color appear where polygons or tile boundaries meet (version 5.2.0).

**Versions Affected**

MapLibre GL JS: 5.2.0 and 5.0.0

**Environment**

Browser: Chrome - version 134.0.6998.118

OS: Windows 11

Framework: Angular 19 (though likely not framework‐specific)

**Additional Context**

- There are none console errors related with this issue.
- This bug seems related to how partial transparency is handled in 3D mode in the newer rendering pipeline, because if transparency were off map renders correctly.

![Image](https://github.com/user-attachments/assets/ae4cfd1a-a846-49ab-a920-1404dc75cce3)
- removing custom raster baselayer does not change behavior:

![Image](https://github.com/user-attachments/assets/b6590222-6d9f-44a0-a109-a250169abc88)

- Rolling back to MapLibre GL JS 4.7.1 resolves the visual artifact completely.

If more information or a minimal reproduction repository is needed, I can provide it.

Thank you!
Lukasz Stempek
[sharpmap.eu](https://sharpmap.eu/)

Closes #5746 (https://github.com/maplibre/maplibre-gl-js/pull/5746)

## Expected

Behavior**
![Image](https://github.com/user-attachments/assets/2dbdc455-a1cb-4848-8c71-9d348b4fe275)

A smooth, semi‐transparent rendering of the forest polygons in 3D, without any noticeable intersecting stripes (version 4.7.1).

**Actual Behavior**

![Image](https://github.com/user-attachments/assets/1625eff5-21f1-4bbc-b61b-82805e1ee46b)

Distinct intersecting stripes of darker or more opaque color appear where polygons or tile boundaries meet (version 5.2.0).

**Versions Affected**

MapLibre GL JS: 5.2.0 and 5.0.0

**Environment**

Browser: Chrome - version 134.0.6998.118

OS: Windows 11

Framework: Angular 19 (though likely not framework‐specific)

**Additional Context**

- There are none console errors related with this issue.
- This bug seems related to how partial transparency is handled in 3D mode in the newer rendering pipeline, because if transparency were off map renders correctly.

![Image](https://github.com/user-attachments/assets/ae4cfd1a-a846-49ab-a920-1404dc75cce3)
- removing custom raster baselayer does not change behavior:

![Image](https://github.com/user-attachments/assets/b6590222-6d9f-44a0-a109-a250169abc88)

- Rolling back to MapLibre GL JS 4.7.1 resolves the visual artifact completely.

If more information or a minimal reproduction repository is needed, I can provide it.

Thank you!
Lukasz Stempek
[sharpmap.eu](https://sharpmap.eu/)

Closes #5746 (https://github.com/maplibre/maplibre-gl-js/pull/5746)

## Actual

Behavior**

![Image](https://github.com/user-attachments/assets/1625eff5-21f1-4bbc-b61b-82805e1ee46b)

Distinct intersecting stripes of darker or more opaque color appear where polygons or tile boundaries meet (version 5.2.0).

**Versions Affected**

MapLibre GL JS: 5.2.0 and 5.0.0

**Environment**

Browser: Chrome - version 134.0.6998.118

OS: Windows 11

Framework: Angular 19 (though likely not framework‐specific)

**Additional Context**

- There are none console errors related with this issue.
- This bug seems related to how partial transparency is handled in 3D mode in the newer rendering pipeline, because if transparency were off map renders correctly.

![Image](https://github.com/user-attachments/assets/ae4cfd1a-a846-49ab-a920-1404dc75cce3)
- removing custom raster baselayer does not change behavior:

![Image](https://github.com/user-attachments/assets/b6590222-6d9f-44a0-a109-a250169abc88)

- Rolling back to MapLibre GL JS 4.7.1 resolves the visual artifact completely.

If more information or a minimal reproduction repository is needed, I can provide it.

Thank you!
Lukasz Stempek
[sharpmap.eu](https://sharpmap.eu/)

Closes #5746 (https://github.com/maplibre/maplibre-gl-js/pull/5746)

## Ground Truth

See fix at https://github.com/maplibre/maplibre-gl-js/pull/5746.

## Fix

```yaml
fix_pr_url: https://github.com/maplibre/maplibre-gl-js/pull/5746
fix_sha: 71f44f9d98c6acb28a9e5aa86757321b5c7b1ea1
bug_class: consumer-misuse
files:
  - src/render/draw_fill.ts
  - src/render/draw_line.ts
  - src/render/painter.ts
```
