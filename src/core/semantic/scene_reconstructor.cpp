#include "src/core/semantic/scene_reconstructor.h"
#include "src/core/semantic/matrix_classifier.h"

#include <algorithm>

namespace gla {

SceneInfo SceneReconstructor::reconstruct(const NormalizedFrame& frame) const {
    SceneInfo info;

    // Step 1: Extract camera.
    info.camera = camera_extractor_.extract(frame);

    // Step 2: Group draw calls into objects.
    info.objects = object_grouper_.group(frame);

    // Step 3: Determine reconstruction quality.
    bool has_camera  = info.camera.has_value();

    // Consider objects "found" if there is at least one with confidence > 0.
    bool has_objects = false;
    bool high_conf_objects = false;
    for (const auto& obj : info.objects) {
        if (obj.confidence > 0.0f) has_objects = true;
        if (obj.confidence > 0.5f) { high_conf_objects = true; break; }
    }

    if (has_camera && high_conf_objects) {
        info.reconstruction_quality = "full";
    } else if (has_camera || has_objects) {
        info.reconstruction_quality = "partial";
    } else {
        info.reconstruction_quality = "raw_only";
    }

    return info;
}

}  // namespace gla
