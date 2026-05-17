/* GL shadow state tracker
 * Mirrors the OpenGL state machine to avoid expensive glGet* calls at capture
 * time. Every intercepted state-setting call updates this shadow; serialization
 * reads from here instead of querying the driver.
 */

#include "src/shims/gl/shadow_state.h"

#include <stddef.h>
#include <string.h>
#include <stdint.h>

/* -------------------------------------------------------------------------
 * Internal helpers
 * ---------------------------------------------------------------------- */

/* Find or allocate a uniform slot for the given location.
 * Returns NULL if the table is full. */
static BhdrShadowUniform *find_or_alloc_uniform(BhdrShadowState *state,
                                                int32_t location) {
    /* Search existing slots first */
    for (uint32_t i = 0; i < state->uniform_count; i++) {
        if (state->uniforms[i].active &&
            (int32_t)state->uniforms[i].location == location) {
            return &state->uniforms[i];
        }
    }
    /* Allocate a new slot */
    if (state->uniform_count >= BHDR_MAX_UNIFORMS) {
        return NULL;
    }
    BhdrShadowUniform *u = &state->uniforms[state->uniform_count++];
    memset(u, 0, sizeof(*u));
    u->location = (uint32_t)location;
    u->active   = true;
    return u;
}

/* -------------------------------------------------------------------------
 * Initialization
 * ---------------------------------------------------------------------- */

void bhdr_shadow_init(BhdrShadowState *state) {
    memset(state, 0, sizeof(*state));

    /* GL spec defaults */
    state->depth_func        = GL_LESS;
    state->depth_write_enabled = true;   /* glDepthMask defaults to GL_TRUE */
    state->front_face        = GL_CCW;
    state->cull_mode         = GL_BACK;

    /* blend_src/blend_dst default: GL_ONE / GL_ZERO — but we zero-init so
     * leave as 0; callers that care about the initial blend equation should
     * call bhdr_shadow_blend_func themselves after init. */
}

/* -------------------------------------------------------------------------
 * Texture
 * ---------------------------------------------------------------------- */

void bhdr_shadow_active_texture(BhdrShadowState *state, uint32_t texture_unit) {
    /* texture_unit is the raw GL enum, e.g. GL_TEXTURE0 + n */
    uint32_t idx = texture_unit - GL_TEXTURE0;
    if (idx < BHDR_MAX_TEXTURE_UNITS) {
        state->active_texture_unit = idx;
    }
}

void bhdr_shadow_bind_texture_2d(BhdrShadowState *state, uint32_t texture_id) {
    if (state->active_texture_unit < BHDR_MAX_TEXTURE_UNITS) {
        state->bound_textures_2d[state->active_texture_unit] = texture_id;
    }
}

void bhdr_shadow_tex_image_2d(BhdrShadowState *state, uint32_t texture_id,
                             uint32_t width, uint32_t height,
                             uint32_t internal_format) {
    if (texture_id > 0 && texture_id < BHDR_MAX_TEXTURES) {
        state->texture_info[texture_id].width           = width;
        state->texture_info[texture_id].height          = height;
        state->texture_info[texture_id].internal_format = internal_format;
    }
}

const BhdrTextureInfo* bhdr_shadow_get_texture_info(const BhdrShadowState *state,
                                                   uint32_t texture_id) {
    if (texture_id > 0 && texture_id < BHDR_MAX_TEXTURES) {
        return &state->texture_info[texture_id];
    }
    return NULL;
}

/* -------------------------------------------------------------------------
 * Shader program
 * ---------------------------------------------------------------------- */

void bhdr_shadow_use_program(BhdrShadowState *state, uint32_t program_id) {
    state->current_program = program_id;
}

/* -------------------------------------------------------------------------
 * Uniforms
 * ---------------------------------------------------------------------- */

void bhdr_shadow_set_uniform_1f(BhdrShadowState *state, int32_t location,
                                float v) {
    BhdrShadowUniform *u = find_or_alloc_uniform(state, location);
    if (!u) return;
    u->type      = GL_FLOAT;
    u->data_size = sizeof(float);
    memcpy(u->data, &v, sizeof(float));
}

void bhdr_shadow_set_uniform_3f(BhdrShadowState *state, int32_t location,
                                float x, float y, float z) {
    BhdrShadowUniform *u = find_or_alloc_uniform(state, location);
    if (!u) return;
    float tmp[3] = {x, y, z};
    u->type      = GL_FLOAT_VEC3;
    u->data_size = 3 * sizeof(float);
    memcpy(u->data, tmp, u->data_size);
}

void bhdr_shadow_set_uniform_4f(BhdrShadowState *state, int32_t location,
                                float x, float y, float z, float w) {
    BhdrShadowUniform *u = find_or_alloc_uniform(state, location);
    if (!u) return;
    float tmp[4] = {x, y, z, w};
    u->type      = GL_FLOAT_VEC4;
    u->data_size = 4 * sizeof(float);
    memcpy(u->data, tmp, u->data_size);
}

void bhdr_shadow_set_uniform_1i(BhdrShadowState *state, int32_t location,
                                int32_t v) {
    BhdrShadowUniform *u = find_or_alloc_uniform(state, location);
    if (!u) return;
    u->type      = GL_INT;
    u->data_size = sizeof(int32_t);
    memcpy(u->data, &v, sizeof(int32_t));
}

void bhdr_shadow_set_uniform_mat4(BhdrShadowState *state, int32_t location,
                                  const float *data) {
    BhdrShadowUniform *u = find_or_alloc_uniform(state, location);
    if (!u) return;
    u->type      = GL_FLOAT_MAT4;
    u->data_size = 16 * sizeof(float);
    memcpy(u->data, data, u->data_size);
}

void bhdr_shadow_set_uniform_mat3(BhdrShadowState *state, int32_t location,
                                  const float *data) {
    BhdrShadowUniform *u = find_or_alloc_uniform(state, location);
    if (!u) return;
    u->type      = GL_FLOAT_MAT3;
    u->data_size = 9 * sizeof(float);
    memcpy(u->data, data, u->data_size);
}

/* -------------------------------------------------------------------------
 * Pipeline state — enable / disable
 * ---------------------------------------------------------------------- */

void bhdr_shadow_enable(BhdrShadowState *state, uint32_t cap) {
    switch (cap) {
        case GL_DEPTH_TEST:   state->depth_test_enabled  = true; break;
        case GL_BLEND:        state->blend_enabled        = true; break;
        case GL_CULL_FACE:    state->cull_enabled         = true; break;
        case GL_SCISSOR_TEST: state->scissor_test_enabled = true; break;
        default: break;
    }
}

void bhdr_shadow_disable(BhdrShadowState *state, uint32_t cap) {
    switch (cap) {
        case GL_DEPTH_TEST:   state->depth_test_enabled  = false; break;
        case GL_BLEND:        state->blend_enabled        = false; break;
        case GL_CULL_FACE:    state->cull_enabled         = false; break;
        case GL_SCISSOR_TEST: state->scissor_test_enabled = false; break;
        default: break;
    }
}

void bhdr_shadow_depth_func(BhdrShadowState *state, uint32_t func) {
    state->depth_func = func;
}

void bhdr_shadow_depth_mask(BhdrShadowState *state, bool flag) {
    state->depth_write_enabled = flag;
}

void bhdr_shadow_blend_func(BhdrShadowState *state, uint32_t src,
                            uint32_t dst) {
    state->blend_src = src;
    state->blend_dst = dst;
}

void bhdr_shadow_cull_face(BhdrShadowState *state, uint32_t mode) {
    state->cull_mode = mode;
}

void bhdr_shadow_front_face(BhdrShadowState *state, uint32_t mode) {
    state->front_face = mode;
}

void bhdr_shadow_viewport(BhdrShadowState *state, int32_t x, int32_t y,
                          int32_t w, int32_t h) {
    state->viewport[0] = x;
    state->viewport[1] = y;
    state->viewport[2] = w;
    state->viewport[3] = h;
}

void bhdr_shadow_scissor(BhdrShadowState *state, int32_t x, int32_t y,
                         int32_t w, int32_t h) {
    state->scissor[0] = x;
    state->scissor[1] = y;
    state->scissor[2] = w;
    state->scissor[3] = h;
}

/* -------------------------------------------------------------------------
 * Buffer bindings
 * ---------------------------------------------------------------------- */

void bhdr_shadow_bind_vao(BhdrShadowState *state, uint32_t vao) {
    state->bound_vao = vao;
}

void bhdr_shadow_bind_buffer(BhdrShadowState *state, uint32_t target,
                             uint32_t buffer) {
    switch (target) {
        case GL_ARRAY_BUFFER:         state->bound_vbo = buffer; break;
        case GL_ELEMENT_ARRAY_BUFFER: state->bound_ebo = buffer; break;
        default: break;
    }
}

void bhdr_shadow_bind_framebuffer(BhdrShadowState *state, uint32_t target,
                                  uint32_t fbo) {
    (void)target; /* GL_FRAMEBUFFER, GL_READ_FRAMEBUFFER, etc. */
    state->bound_fbo = fbo;
}

/* -------------------------------------------------------------------------
 * FBO attachment tracking
 * ---------------------------------------------------------------------- */

void bhdr_shadow_framebuffer_texture_2d(BhdrShadowState *state, uint32_t target,
                                        uint32_t attachment, uint32_t texture) {
    (void)target; /* GL_FRAMEBUFFER */
    uint32_t fbo_id = state->bound_fbo;
    if (fbo_id == 0) return; /* default FBO — nothing to track */

    /* Find existing slot for this FBO, or allocate a new one */
    BhdrFboInfo *slot = NULL;
    for (uint32_t i = 0; i < state->fbo_count; i++) {
        if (state->fbo_info[i].fbo_id == fbo_id) {
            slot = &state->fbo_info[i];
            break;
        }
    }
    if (!slot) {
        if (state->fbo_count >= BHDR_MAX_FBOS) return; /* table full */
        slot = &state->fbo_info[state->fbo_count];
        memset(slot, 0, sizeof(*slot));
        slot->fbo_id = fbo_id;
        state->fbo_count++;
    }

    if (attachment >= GL_COLOR_ATTACHMENT0 &&
        attachment <  GL_COLOR_ATTACHMENT0 + BHDR_MAX_COLOR_ATTACHMENTS) {
        uint32_t idx = attachment - GL_COLOR_ATTACHMENT0;
        slot->color_attachments[idx] = texture;
        if (idx == 0) {
            slot->color_attachment_tex = texture; /* backward compat mirror */
        }
    } else if (attachment == GL_DEPTH_ATTACHMENT) {
        slot->depth_attachment_tex = texture;
    }
}

const BhdrFboInfo* bhdr_shadow_get_fbo_info(const BhdrShadowState *state,
                                            uint32_t fbo_id) {
    for (uint32_t i = 0; i < state->fbo_count; i++) {
        if (state->fbo_info[i].fbo_id == fbo_id) {
            return &state->fbo_info[i];
        }
    }
    return NULL;
}

/* -------------------------------------------------------------------------
 * Draw call tracking
 * ---------------------------------------------------------------------- */

void bhdr_shadow_record_draw(BhdrShadowState *state) {
    state->draw_call_count++;
}

void bhdr_shadow_record_clear(BhdrShadowState *state, uint32_t mask) {
    if (state->clear_count >= BHDR_MAX_CLEARS_PER_FRAME) return;
    BhdrClearRecord *r = &state->clear_records[state->clear_count];
    r->mask             = mask;
    r->draw_call_before = state->draw_call_count;
    state->clear_count++;
}

/* -------------------------------------------------------------------------
 * Frame boundary
 * ---------------------------------------------------------------------- */

void bhdr_shadow_new_frame(BhdrShadowState *state) {
    state->frame_number++;
    state->draw_call_count = 0;
    state->clear_count     = 0;
}

/* -------------------------------------------------------------------------
 * Debug groups (GL_KHR_debug)
 * ---------------------------------------------------------------------- */

void bhdr_shadow_push_debug_group(BhdrShadowState *state, uint32_t id,
                                  const char *name) {
    if (state->debug_group_depth >= BHDR_MAX_DEBUG_GROUP_DEPTH) {
        return;
    }
    BhdrDebugGroupEntry *entry = &state->debug_group_stack[state->debug_group_depth];
    strncpy(entry->name, name, BHDR_MAX_DEBUG_GROUP_NAME - 1);
    entry->name[BHDR_MAX_DEBUG_GROUP_NAME - 1] = '\0';
    entry->id = id;
    state->debug_group_depth++;
}

void bhdr_shadow_pop_debug_group(BhdrShadowState *state) {
    if (state->debug_group_depth > 0) {
        state->debug_group_depth--;
    }
}

int bhdr_shadow_get_debug_group_path(const BhdrShadowState *state, char *buf,
                                     size_t buf_size) {
    if (buf_size == 0) {
        return 0;
    }
    int written = 0;
    for (uint32_t i = 0; i < state->debug_group_depth; i++) {
        if (i > 0) {
            if ((size_t)(written + 1) < buf_size) {
                buf[written++] = '/';
            }
        }
        const char *name = state->debug_group_stack[i].name;
        size_t remaining = buf_size - (size_t)written - 1;
        size_t name_len = strlen(name);
        if (name_len > remaining) {
            name_len = remaining;
        }
        memcpy(buf + written, name, name_len);
        written += (int)name_len;
    }
    buf[written] = '\0';
    return written;
}

int bhdr_shadow_get_debug_group_name(const BhdrShadowState *state,
                                    uint32_t index,
                                    char *buf,
                                    size_t buf_size) {
    if (buf_size == 0) {
        return 0;
    }
    if (index >= state->debug_group_depth) {
        buf[0] = '\0';
        return 0;
    }
    const char *name = state->debug_group_stack[index].name;
    size_t name_len = strlen(name);
    if (name_len + 1 > buf_size) {
        name_len = buf_size - 1;
    }
    memcpy(buf, name, name_len);
    buf[name_len] = '\0';
    return (int)name_len;
}
