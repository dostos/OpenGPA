## User Report

Hi,
I’m using **MapLibre GL JS v5.15.0** inside a **Flutter WebView** environment. In some cases I’m seeing a rendering artifact on the border between a **loaded terrain tile** and a **not-yet-loaded tile** - only when the map is tilted..

### Problem description

At the boundary between tiles, when the neighboring tile is not loaded yet, a visible **vertical “wall” / border** appears — **as if the last row of pixels is extruded downwards to zero elevation**. This artifact occurs when pitch != 0. It looks like a rendering glitch.
Once the missing tile is loaded, the wall disappears.
Screenshot example:
<img width="740" height="504" alt="Image" src="https://github.com/user-attachments/assets/8dabb5f1-8bfe-477a-82c3-1ee16e4cdac2" />

### Steps to Trigger Behavior
1. Tilt the map
2. Pan the map toward an area where neighboring tiles are not yet loaded.
3. Observe the vertical “edge wall” at the tile boundary.

### Expected behavior
If a neighboring tile is not yet available, the map should ideally keep the previous geometry/height
instead of rendering a vertical drop-off

### Question
Is there any way to disable this “edge wall” effect?

Any hints would be greatly appreciated. Thanks in advance!

Closes #7523 (https://github.com/maplibre/maplibre-gl-js/pull/7523)

## Expected

behavior
If a neighboring tile is not yet available, the map should ideally keep the previous geometry/height
instead of rendering a vertical drop-off

## Ground Truth

See fix at https://github.com/maplibre/maplibre-gl-js/pull/7523.

## Fix

```yaml
fix_pr_url: https://github.com/maplibre/maplibre-gl-js/pull/7523
fix_sha: 15638c89ac024583e8dc5a0ad8c82b280cc0bc20
fix_parent_sha: 039f43a4c2f3d4d9476097446d7ee98a75d6bd9c
bug_class: consumer-misuse
files:
  - src/render/terrain.ts
  - src/ui/map.ts
  - src/webgl/draw/draw_terrain.ts
```
