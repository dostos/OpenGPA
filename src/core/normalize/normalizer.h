#pragma once
#include "src/core/normalize/normalized_types.h"
#include "src/core/store/raw_frame.h"

namespace gpa {

class Normalizer {
public:
    virtual ~Normalizer() = default;
    // Convert a raw frame to normalized representation
    virtual NormalizedFrame normalize(const gpa::store::RawFrame& raw) const;
};

}  // namespace gpa
