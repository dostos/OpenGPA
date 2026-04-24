#!/bin/bash
# Snapshot mapping helper for Round 10 scenarios.
# Echoes the absolute path to an upstream snapshot for a given scenario name.
# Returns empty string if no snapshot is mapped.
get_snapshot_for_scenario() {
  case "$1" in
    r2_certain_effects_produce_invalid_alpha_va)      echo "/data3/opengpa-snapshots/postprocessing" ;;
    r6_to_create_an_orm_texture_an_incorrect_va)      echo "/data3/opengpa-snapshots/postprocessing" ;;
    r11_screen_glitch_with_bloom_on_m1_mac)           echo "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3" ;;
    r11_webglrenderer_ubo_uniform_buffer_object_)     echo "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3" ;;
    r14_webgpurenderer_make_colored_shadows_opti)     echo "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3" ;;
    r17_incorrect_clipping_with_global_clipping_)     echo "/data3/opengpa-snapshots/github_com__mrdoob__three__7690b5090676" ;;
    r17_mapbox_gl_js_image_overlay_coordinates_p)     echo "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e" ;;
    r18_raster_tiles_aren_t_perfectly_crisp_at_i)     echo "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e" ;;
    r24_logarithmicdepthbuffer_causes_reflector_)     echo "/data3/opengpa-snapshots/github_com__mrdoob__three__cf60b969c46b" ;;
    *) echo "" ;;
  esac
}

get_framework_for_scenario() {
  case "$1" in
    r2_*|r6_*) echo "postprocessing" ;;
    r11_screen_glitch*|r11_webgl*|r14_webgpu*|r17_incorrect_clipping*|r24_logarithmic*) echo "three.js" ;;
    r17_mapbox*|r18_raster*) echo "mapbox-gl-js" ;;
    *) echo "the framework" ;;
  esac
}
