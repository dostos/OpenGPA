#pragma once
#include <cstdint>
#include <vector>
#include <string>

namespace gla::store {

// Represents raw data for a single draw call as captured by the shim
struct RawDrawCall {
    uint32_t id;
    uint32_t primitive_type;  // GL enum
    uint32_t vertex_count;
    uint32_t index_count;
    uint32_t instance_count;
    uint32_t shader_program_id;

    // Shader parameters (serialized from FlatBuffer)
    struct Param {
        std::string name;
        uint32_t type;
        std::vector<uint8_t> data;
    };
    std::vector<Param> params;

    // Texture bindings
    struct Texture {
        uint32_t slot;
        uint32_t texture_id;
        uint32_t width, height, format;
    };
    std::vector<Texture> textures;

    // Pipeline state
    struct Pipeline {
        int32_t viewport[4];
        int32_t scissor[4];
        bool scissor_enabled;
        bool depth_test, depth_write;
        uint32_t depth_func;
        bool blend_enabled;
        uint32_t blend_src, blend_dst;
        bool cull_enabled;
        uint32_t cull_mode, front_face;
    } pipeline;

    // Bulk data (vertex buffer, index buffer contents)
    std::vector<uint8_t> vertex_data;
    std::vector<uint8_t> index_data;

    // Vertex attributes
    struct VertexAttr {
        uint32_t location, format, components, stride, offset;
    };
    std::vector<VertexAttr> attributes;
};

// A captured frame
struct RawFrame {
    uint64_t frame_id;
    double timestamp;
    uint32_t api_type;  // 0=GL, 1=VK, 2=WebGL

    std::vector<RawDrawCall> draw_calls;

    // Framebuffer data
    uint32_t fb_width, fb_height;
    std::vector<uint8_t> fb_color;    // RGBA, size = w*h*4
    std::vector<float> fb_depth;      // size = w*h
    std::vector<uint8_t> fb_stencil;  // size = w*h
};

}  // namespace gla::store
