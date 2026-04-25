#!/bin/bash
# Snapshot mapping helper for R10v2 + R11 scenarios.
# Echoes the absolute path to an upstream snapshot for a given scenario name.
# Returns empty string if no snapshot is mapped.
get_snapshot_for_scenario() {
  case "$1" in
    # R10v2 set
    r2_certain_effects_produce_invalid_alpha_va)      echo "/data3/opengpa-snapshots/postprocessing" ;;
    r11_screen_glitch_with_bloom_on_m1_mac)           echo "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3" ;;
    r11_webglrenderer_ubo_uniform_buffer_object_)     echo "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3" ;;
    r14_webgpurenderer_make_colored_shadows_opti)     echo "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3" ;;
    r17_mapbox_gl_js_image_overlay_coordinates_p)     echo "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e" ;;
    r18_raster_tiles_aren_t_perfectly_crisp_at_i)     echo "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e" ;;
    # R11 breadcrumb set
    r53_hemispherelightprobe_intensity_wrong_)        echo "/data3/opengpa-snapshots/github_com__mrdoob__three__f8509646d78f" ;;
    r54_black_squares_when_rendering_glass_ma)        echo "/data3/opengpa-snapshots/github_com__mrdoob__three__bfe332d9ee70" ;;
    r55_certain_gltf_models_not_receiving_sha)        echo "/data3/opengpa-snapshots/github_com__mrdoob__three__f3fa844ba4ca" ;;
    r56_conegeometry_has_wrong_side_faces_and)        echo "/data3/opengpa-snapshots/github_com__mrdoob__three__8be6bed537fe" ;;
    r57_ktx2_texture_with_alphahash_renders_a)        echo "/data3/opengpa-snapshots/github_com__mrdoob__three__fb28a2e295a5" ;;
    *) echo "" ;;
  esac
}
