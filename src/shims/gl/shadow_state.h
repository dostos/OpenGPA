#ifndef BHDR_SHADOW_STATE_H
#define BHDR_SHADOW_STATE_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#define BHDR_MAX_TEXTURE_UNITS 32
#define BHDR_MAX_UNIFORMS 256
#define BHDR_MAX_VERTEX_ATTRIBS 16
#define BHDR_MAX_TEXTURES 4096
#define BHDR_MAX_DEBUG_GROUP_DEPTH 32
#define BHDR_MAX_DEBUG_GROUP_NAME 128
#define BHDR_MAX_CLEARS_PER_FRAME 16
#define BHDR_MAX_FBOS 64

typedef struct {
    char name[BHDR_MAX_DEBUG_GROUP_NAME];
    uint32_t id;
} BhdrDebugGroupEntry;

typedef struct {
    uint32_t mask;             /* GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT */
    uint32_t draw_call_before; /* how many draw calls happened before this clear */
} BhdrClearRecord;

/* GL enum constants (no GL headers needed) */
#define GL_TEXTURE0             0x84C0
#define GL_TEXTURE_2D           0x0DE1
#define GL_DEPTH_TEST           0x0B71
#define GL_BLEND                0x0BE2
#define GL_CULL_FACE            0x0B44
#define GL_SCISSOR_TEST         0x0C11
#define GL_LESS                 0x0201
#define GL_LEQUAL               0x0203
#define GL_BACK                 0x0405
#define GL_CCW                  0x0901
#define GL_ARRAY_BUFFER         0x8892
#define GL_ELEMENT_ARRAY_BUFFER 0x8893
#define GL_FRAMEBUFFER          0x8D40
#define GL_FLOAT                0x1406
#define GL_FLOAT_VEC3           0x8B51
#define GL_FLOAT_VEC4           0x8B52
#define GL_FLOAT_MAT3           0x8B5B
#define GL_FLOAT_MAT4           0x8B5C
#define GL_INT                  0x1404
#define GL_COLOR_ATTACHMENT0    0x8CE0
#define GL_DEPTH_ATTACHMENT     0x8D00

/* Uniform value (up to mat4 = 16 floats = 64 bytes) */
typedef struct {
    uint32_t location;
    uint32_t type;       /* GL type enum */
    uint8_t  data[64];   /* raw value bytes */
    uint32_t data_size;  /* actual size used */
    char     name[64];   /* uniform name (if known) */
    bool     active;
} BhdrShadowUniform;

/* Per-texture dimension/format info, populated by glTexImage2D intercept */
typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t internal_format;
} BhdrTextureInfo;

/* Per-FBO attachment tracking */
#define BHDR_MAX_COLOR_ATTACHMENTS 8
typedef struct {
    uint32_t fbo_id;
    /* Texture IDs for GL_COLOR_ATTACHMENT0..7. Slot 0 mirrors
     * color_attachment_tex below for backward compat.  A value of 0 in slot i
     * means "no texture attached at COLOR_ATTACHMENT<i>". */
    uint32_t color_attachments[BHDR_MAX_COLOR_ATTACHMENTS];
    uint32_t color_attachment_tex;   /* texture ID attached as COLOR_ATTACHMENT0 (== color_attachments[0]) */
    uint32_t depth_attachment_tex;   /* texture ID attached as DEPTH_ATTACHMENT */
} BhdrFboInfo;

typedef struct {
    /* Texture bindings */
    uint32_t active_texture_unit;                       /* 0-based index */
    uint32_t bound_textures_2d[BHDR_MAX_TEXTURE_UNITS];

    /* Per-texture metadata (indexed by texture name/id) */
    BhdrTextureInfo texture_info[BHDR_MAX_TEXTURES];

    /* Shader program */
    uint32_t        current_program;
    BhdrShadowUniform uniforms[BHDR_MAX_UNIFORMS];
    uint32_t        uniform_count;

    /* Pipeline state */
    int32_t  viewport[4];           /* x, y, w, h */
    int32_t  scissor[4];            /* x, y, w, h */
    bool     depth_test_enabled;
    bool     depth_write_enabled;
    uint32_t depth_func;            /* GL_LESS, GL_LEQUAL, etc. */
    bool     blend_enabled;
    uint32_t blend_src;
    uint32_t blend_dst;
    bool     cull_enabled;
    uint32_t cull_mode;             /* GL_BACK, GL_FRONT */
    uint32_t front_face;            /* GL_CCW, GL_CW */
    bool     scissor_test_enabled;

    /* Buffer bindings */
    uint32_t bound_vao;
    uint32_t bound_vbo;             /* GL_ARRAY_BUFFER */
    uint32_t bound_ebo;             /* GL_ELEMENT_ARRAY_BUFFER */
    uint32_t bound_fbo;             /* GL_FRAMEBUFFER */

    /* FBO attachment tracking */
    BhdrFboInfo fbo_info[BHDR_MAX_FBOS];
    uint32_t fbo_count;

    /* Frame tracking */
    uint64_t frame_number;
    uint32_t draw_call_count;       /* resets each frame */

    /* Per-frame clear records */
    BhdrClearRecord clear_records[BHDR_MAX_CLEARS_PER_FRAME];
    uint32_t clear_count;           /* resets each frame */

    /* Debug group stack (GL_KHR_debug) */
    BhdrDebugGroupEntry debug_group_stack[BHDR_MAX_DEBUG_GROUP_DEPTH];
    uint32_t debug_group_depth;
} BhdrShadowState;

/* Initialize to GL defaults */
void bhdr_shadow_init(BhdrShadowState *state);

/* Texture */
void bhdr_shadow_active_texture(BhdrShadowState *state, uint32_t texture_unit); /* GL_TEXTURE0+n */
void bhdr_shadow_bind_texture_2d(BhdrShadowState *state, uint32_t texture_id);
void bhdr_shadow_tex_image_2d(BhdrShadowState *state, uint32_t texture_id,
                             uint32_t width, uint32_t height, uint32_t internal_format);
const BhdrTextureInfo* bhdr_shadow_get_texture_info(const BhdrShadowState *state, uint32_t texture_id);

/* Shader */
void bhdr_shadow_use_program(BhdrShadowState *state, uint32_t program_id);

/* Uniforms */
void bhdr_shadow_set_uniform_1f(BhdrShadowState *state, int32_t location, float v);
void bhdr_shadow_set_uniform_3f(BhdrShadowState *state, int32_t location, float x, float y, float z);
void bhdr_shadow_set_uniform_4f(BhdrShadowState *state, int32_t location, float x, float y, float z, float w);
void bhdr_shadow_set_uniform_1i(BhdrShadowState *state, int32_t location, int32_t v);
void bhdr_shadow_set_uniform_mat4(BhdrShadowState *state, int32_t location, const float *data);
void bhdr_shadow_set_uniform_mat3(BhdrShadowState *state, int32_t location, const float *data);

/* Pipeline state */
void bhdr_shadow_enable(BhdrShadowState *state, uint32_t cap);
void bhdr_shadow_disable(BhdrShadowState *state, uint32_t cap);
void bhdr_shadow_depth_func(BhdrShadowState *state, uint32_t func);
void bhdr_shadow_depth_mask(BhdrShadowState *state, bool flag);
void bhdr_shadow_blend_func(BhdrShadowState *state, uint32_t src, uint32_t dst);
void bhdr_shadow_cull_face(BhdrShadowState *state, uint32_t mode);
void bhdr_shadow_front_face(BhdrShadowState *state, uint32_t mode);
void bhdr_shadow_viewport(BhdrShadowState *state, int32_t x, int32_t y, int32_t w, int32_t h);
void bhdr_shadow_scissor(BhdrShadowState *state, int32_t x, int32_t y, int32_t w, int32_t h);

/* Buffer bindings */
void bhdr_shadow_bind_vao(BhdrShadowState *state, uint32_t vao);
void bhdr_shadow_bind_buffer(BhdrShadowState *state, uint32_t target, uint32_t buffer);
void bhdr_shadow_bind_framebuffer(BhdrShadowState *state, uint32_t target, uint32_t fbo);

/* FBO attachment tracking */
void bhdr_shadow_framebuffer_texture_2d(BhdrShadowState *state, uint32_t target,
                                        uint32_t attachment, uint32_t texture);
const BhdrFboInfo* bhdr_shadow_get_fbo_info(const BhdrShadowState *state, uint32_t fbo_id);

/* Draw call tracking */
void bhdr_shadow_record_draw(BhdrShadowState *state);

/* Clear tracking */
void bhdr_shadow_record_clear(BhdrShadowState *state, uint32_t mask);

/* Frame boundary */
void bhdr_shadow_new_frame(BhdrShadowState *state);

/* Debug groups (GL_KHR_debug) */
void bhdr_shadow_push_debug_group(BhdrShadowState *state, uint32_t id, const char *name);
void bhdr_shadow_pop_debug_group(BhdrShadowState *state);
int  bhdr_shadow_get_debug_group_path(const BhdrShadowState *state, char *buf, size_t buf_size);
/* Get the i-th debug group name (0-indexed). Returns the string length
 * written into ``buf`` (excluding the NUL terminator) on success, or 0 if
 * the index is out of range. ``buf`` is always NUL-terminated. */
int  bhdr_shadow_get_debug_group_name(const BhdrShadowState *state,
                                     uint32_t index,
                                     char *buf,
                                     size_t buf_size);

#endif /* BHDR_SHADOW_STATE_H */
