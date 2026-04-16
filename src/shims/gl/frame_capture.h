#ifndef GLA_FRAME_CAPTURE_H
#define GLA_FRAME_CAPTURE_H

#include "shadow_state.h"
#include <stdint.h>

/* Called from glXSwapBuffers wrapper. Captures the current framebuffer (color
 * + depth) into a shared memory slot and notifies the engine via the IPC
 * socket. No-op when the IPC client is not connected (passthrough mode). */
void gla_frame_on_swap(void);

/* Record draw call metadata from the current shadow state snapshot.
 * Call from each draw call wrapper (glDrawArrays, glDrawElements, etc.)
 * before returning. No-op when IPC is not connected.
 *   shadow         - current shadow state (all GL state tracked so far)
 *   primitive      - GL primitive type enum (e.g. GL_TRIANGLES)
 *   vertex_count   - number of vertices (count arg to glDrawArrays, or
 *                    derived from index count for glDrawElements)
 *   index_count    - number of indices (0 for non-indexed draws)
 *   instance_count - instance count (1 for non-instanced draws)
 */
void gla_frame_record_draw_call(const GlaShadowState* shadow,
                                 uint32_t primitive,
                                 uint32_t vertex_count,
                                 uint32_t index_count,
                                 uint32_t instance_count);

/* Reset per-frame draw call recording buffer. Called at the start of each
 * frame (i.e. when gla_shadow_new_frame is called). */
void gla_frame_reset_draw_calls(void);

#endif /* GLA_FRAME_CAPTURE_H */
