## User Report

I'm trying to change the color of a geoJSON marker by using "icon-color". It does have an image supplied, as the style reference indicates it requires, but the icon remains the default color. text-color is working correctly as expected.

JS fiddle example: https://jsfiddle.net/x6dr7sek/4/

## Ground Truth

See fix at https://github.com/mapbox/mapbox-gl-js/pull/5181.

## Fix

```yaml
fix_pr_url: https://github.com/mapbox/mapbox-gl-js/pull/5181
fix_sha: 0cbc71d77532db1ec29fe62ebd90d6cdf2caed80
bug_class: consumer-misuse
files:
  - src/symbol/sprite_atlas.js
  - src/ui/map.js
```
