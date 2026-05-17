#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include "gl_wrappers.h"
#include "shadow_state.h"
#include "frame_capture.h"
#include "native_trace.h"

/* Declared in gl_shim.c */
extern BhdrShadowState bhdr_shadow;
void bhdr_init(void);

/* Native-trace scan hook. Fires on glUniform* / glBindTexture in gated
 * mode, matching the browser JS scanner.
 *
 *   BHDR_TRACE_NATIVE=1        → globals scan (Phase 1)
 *   BHDR_TRACE_NATIVE_STACK=1  → stack-local scan (Phase 2)
 *
 * Both env vars are independent; either or both may be enabled. Each scan
 * is a no-op unless its scanner was successfully initialised. */
static inline void bhdr_trace_gated(void) {
    if (bhdr_native_trace_is_enabled()) {
        bhdr_native_trace_scan(bhdr_shadow.frame_number,
                              bhdr_shadow.draw_call_count);
    }
    if (bhdr_native_trace_stack_is_enabled()) {
        bhdr_native_trace_scan_stack(bhdr_shadow.frame_number,
                                    bhdr_shadow.draw_call_count);
    }
}

/* --------------------------------------------------------------------------
 * Dispatch table initialization
 * -------------------------------------------------------------------------- */

void bhdr_wrappers_init(void) {
    bhdr_real_gl.glDrawArrays            = dlsym(RTLD_NEXT, "glDrawArrays");
    bhdr_real_gl.glDrawElements          = dlsym(RTLD_NEXT, "glDrawElements");
    bhdr_real_gl.glDrawArraysInstanced   = dlsym(RTLD_NEXT, "glDrawArraysInstanced");
    bhdr_real_gl.glDrawElementsInstanced = dlsym(RTLD_NEXT, "glDrawElementsInstanced");

    bhdr_real_gl.glUseProgram        = dlsym(RTLD_NEXT, "glUseProgram");
    bhdr_real_gl.glUniform1f         = dlsym(RTLD_NEXT, "glUniform1f");
    bhdr_real_gl.glUniform3f         = dlsym(RTLD_NEXT, "glUniform3f");
    bhdr_real_gl.glUniform4f         = dlsym(RTLD_NEXT, "glUniform4f");
    bhdr_real_gl.glUniform1i         = dlsym(RTLD_NEXT, "glUniform1i");
    bhdr_real_gl.glUniformMatrix4fv  = dlsym(RTLD_NEXT, "glUniformMatrix4fv");
    bhdr_real_gl.glUniformMatrix3fv  = dlsym(RTLD_NEXT, "glUniformMatrix3fv");

    bhdr_real_gl.glActiveTexture = dlsym(RTLD_NEXT, "glActiveTexture");
    bhdr_real_gl.glBindTexture   = dlsym(RTLD_NEXT, "glBindTexture");
    bhdr_real_gl.glTexImage2D    = dlsym(RTLD_NEXT, "glTexImage2D");

    bhdr_real_gl.glClear       = dlsym(RTLD_NEXT, "glClear");

    bhdr_real_gl.glEnable      = dlsym(RTLD_NEXT, "glEnable");
    bhdr_real_gl.glDisable     = dlsym(RTLD_NEXT, "glDisable");
    bhdr_real_gl.glDepthFunc   = dlsym(RTLD_NEXT, "glDepthFunc");
    bhdr_real_gl.glDepthMask   = dlsym(RTLD_NEXT, "glDepthMask");
    bhdr_real_gl.glBlendFunc   = dlsym(RTLD_NEXT, "glBlendFunc");
    bhdr_real_gl.glCullFace    = dlsym(RTLD_NEXT, "glCullFace");
    bhdr_real_gl.glFrontFace   = dlsym(RTLD_NEXT, "glFrontFace");
    bhdr_real_gl.glViewport    = dlsym(RTLD_NEXT, "glViewport");
    bhdr_real_gl.glScissor     = dlsym(RTLD_NEXT, "glScissor");

    bhdr_real_gl.glBindVertexArray      = dlsym(RTLD_NEXT, "glBindVertexArray");
    bhdr_real_gl.glBindBuffer           = dlsym(RTLD_NEXT, "glBindBuffer");
    bhdr_real_gl.glBindFramebuffer      = dlsym(RTLD_NEXT, "glBindFramebuffer");
    bhdr_real_gl.glFramebufferTexture2D = dlsym(RTLD_NEXT, "glFramebufferTexture2D");

    bhdr_real_gl.glReadPixels   = dlsym(RTLD_NEXT, "glReadPixels");
    bhdr_real_gl.glGetIntegerv  = dlsym(RTLD_NEXT, "glGetIntegerv");

    bhdr_real_gl.glPushDebugGroup = dlsym(RTLD_NEXT, "glPushDebugGroup");
    bhdr_real_gl.glPopDebugGroup  = dlsym(RTLD_NEXT, "glPopDebugGroup");

    bhdr_real_gl.glXSwapBuffers        = dlsym(RTLD_NEXT, "glXSwapBuffers");
    bhdr_real_gl.glXGetProcAddressARB  = dlsym(RTLD_NEXT, "glXGetProcAddressARB");

    bhdr_real_gl.eglSwapBuffers        = dlsym(RTLD_NEXT, "eglSwapBuffers");
}

/* --------------------------------------------------------------------------
 * Draw call wrappers
 * -------------------------------------------------------------------------- */

void glDrawArrays(GLenum mode, GLint first, GLsizei count) {
    bhdr_init();
    bhdr_real_gl.glDrawArrays(mode, first, count);
    bhdr_shadow_record_draw(&bhdr_shadow);
    bhdr_frame_record_draw_call(&bhdr_shadow, (uint32_t)mode,
                               (uint32_t)count, /*index_count=*/0,
                               /*index_type=*/0,
                               /*instance_count=*/1);
    (void)first;
}

void glDrawElements(GLenum mode, GLsizei count, GLenum type, const void* indices) {
    bhdr_init();
    bhdr_real_gl.glDrawElements(mode, count, type, indices);
    bhdr_shadow_record_draw(&bhdr_shadow);
    bhdr_frame_record_draw_call(&bhdr_shadow, (uint32_t)mode,
                               /*vertex_count=*/(uint32_t)count,
                               /*index_count=*/(uint32_t)count,
                               /*index_type=*/(uint32_t)type,
                               /*instance_count=*/1);
    (void)indices;
}

void glDrawArraysInstanced(GLenum mode, GLint first, GLsizei count, GLsizei instancecount) {
    bhdr_init();
    bhdr_real_gl.glDrawArraysInstanced(mode, first, count, instancecount);
    bhdr_shadow_record_draw(&bhdr_shadow);
    bhdr_frame_record_draw_call(&bhdr_shadow, (uint32_t)mode,
                               (uint32_t)count, /*index_count=*/0,
                               /*index_type=*/0,
                               (uint32_t)instancecount);
    (void)first;
}

void glDrawElementsInstanced(GLenum mode, GLsizei count, GLenum type,
                              const void* indices, GLsizei instancecount) {
    bhdr_init();
    bhdr_real_gl.glDrawElementsInstanced(mode, count, type, indices, instancecount);
    bhdr_shadow_record_draw(&bhdr_shadow);
    bhdr_frame_record_draw_call(&bhdr_shadow, (uint32_t)mode,
                               /*vertex_count=*/(uint32_t)count,
                               /*index_count=*/(uint32_t)count,
                               /*index_type=*/(uint32_t)type,
                               (uint32_t)instancecount);
    (void)indices;
}

/* --------------------------------------------------------------------------
 * Shader wrappers
 * -------------------------------------------------------------------------- */

void glUseProgram(GLuint program) {
    bhdr_init();
    bhdr_real_gl.glUseProgram(program);
    bhdr_shadow_use_program(&bhdr_shadow, program);
}

void glUniform1f(GLint location, GLfloat v0) {
    bhdr_init();
    bhdr_real_gl.glUniform1f(location, v0);
    bhdr_shadow_set_uniform_1f(&bhdr_shadow, location, v0);
    bhdr_trace_gated();
}

void glUniform3f(GLint location, GLfloat v0, GLfloat v1, GLfloat v2) {
    bhdr_init();
    bhdr_real_gl.glUniform3f(location, v0, v1, v2);
    bhdr_shadow_set_uniform_3f(&bhdr_shadow, location, v0, v1, v2);
    bhdr_trace_gated();
}

void glUniform4f(GLint location, GLfloat v0, GLfloat v1, GLfloat v2, GLfloat v3) {
    bhdr_init();
    bhdr_real_gl.glUniform4f(location, v0, v1, v2, v3);
    bhdr_shadow_set_uniform_4f(&bhdr_shadow, location, v0, v1, v2, v3);
    bhdr_trace_gated();
}

void glUniform1i(GLint location, GLint v0) {
    bhdr_init();
    bhdr_real_gl.glUniform1i(location, v0);
    bhdr_shadow_set_uniform_1i(&bhdr_shadow, location, v0);
    bhdr_trace_gated();
}

void glUniformMatrix4fv(GLint location, GLsizei count, GLboolean transpose,
                         const GLfloat* value) {
    bhdr_init();
    bhdr_real_gl.glUniformMatrix4fv(location, count, transpose, value);
    bhdr_shadow_set_uniform_mat4(&bhdr_shadow, location, value);
    bhdr_trace_gated();
}

void glUniformMatrix3fv(GLint location, GLsizei count, GLboolean transpose,
                         const GLfloat* value) {
    bhdr_init();
    bhdr_real_gl.glUniformMatrix3fv(location, count, transpose, value);
    bhdr_shadow_set_uniform_mat3(&bhdr_shadow, location, value);
    bhdr_trace_gated();
}

/* --------------------------------------------------------------------------
 * Texture wrappers
 * -------------------------------------------------------------------------- */

void glActiveTexture(GLenum texture) {
    bhdr_init();
    bhdr_real_gl.glActiveTexture(texture);
    bhdr_shadow_active_texture(&bhdr_shadow, texture);
}

void glBindTexture(GLenum target, GLuint texture) {
    bhdr_init();
    bhdr_real_gl.glBindTexture(target, texture);
    if (target == GL_TEXTURE_2D) {
        bhdr_shadow_bind_texture_2d(&bhdr_shadow, texture);
    }
    bhdr_trace_gated();
}

void glTexImage2D(GLenum target, GLint level, GLint internalformat,
                  GLsizei width, GLsizei height, GLint border,
                  GLenum format, GLenum type, const void* pixels) {
    bhdr_init();
    bhdr_real_gl.glTexImage2D(target, level, internalformat, width, height,
                             border, format, type, pixels);
    /* Track texture dimensions for level 0 of GL_TEXTURE_2D */
    if (target == GL_TEXTURE_2D && level == 0) {
        uint32_t tex_id = bhdr_shadow.bound_textures_2d[bhdr_shadow.active_texture_unit];
        if (tex_id > 0) {
            bhdr_shadow_tex_image_2d(&bhdr_shadow, tex_id,
                                    (uint32_t)width, (uint32_t)height,
                                    (uint32_t)internalformat);
        }
    }
}

/* --------------------------------------------------------------------------
 * Clear wrapper
 * -------------------------------------------------------------------------- */

void glClear(GLbitfield mask) {
    bhdr_init();
    bhdr_real_gl.glClear(mask);
    bhdr_shadow_record_clear(&bhdr_shadow, (uint32_t)mask);
}

/* --------------------------------------------------------------------------
 * Pipeline state wrappers
 * -------------------------------------------------------------------------- */

void glEnable(GLenum cap) {
    bhdr_init();
    bhdr_real_gl.glEnable(cap);
    bhdr_shadow_enable(&bhdr_shadow, cap);
}

void glDisable(GLenum cap) {
    bhdr_init();
    bhdr_real_gl.glDisable(cap);
    bhdr_shadow_disable(&bhdr_shadow, cap);
}

void glDepthFunc(GLenum func) {
    bhdr_init();
    bhdr_real_gl.glDepthFunc(func);
    bhdr_shadow_depth_func(&bhdr_shadow, func);
}

void glDepthMask(GLboolean flag) {
    bhdr_init();
    bhdr_real_gl.glDepthMask(flag);
    bhdr_shadow_depth_mask(&bhdr_shadow, (bool)flag);
}

void glBlendFunc(GLenum sfactor, GLenum dfactor) {
    bhdr_init();
    bhdr_real_gl.glBlendFunc(sfactor, dfactor);
    bhdr_shadow_blend_func(&bhdr_shadow, sfactor, dfactor);
}

void glCullFace(GLenum mode) {
    bhdr_init();
    bhdr_real_gl.glCullFace(mode);
    bhdr_shadow_cull_face(&bhdr_shadow, mode);
}

void glFrontFace(GLenum mode) {
    bhdr_init();
    bhdr_real_gl.glFrontFace(mode);
    bhdr_shadow_front_face(&bhdr_shadow, mode);
}

void glViewport(GLint x, GLint y, GLsizei width, GLsizei height) {
    bhdr_init();
    bhdr_real_gl.glViewport(x, y, width, height);
    bhdr_shadow_viewport(&bhdr_shadow, x, y, width, height);
}

void glScissor(GLint x, GLint y, GLsizei width, GLsizei height) {
    bhdr_init();
    bhdr_real_gl.glScissor(x, y, width, height);
    bhdr_shadow_scissor(&bhdr_shadow, x, y, width, height);
}

/* --------------------------------------------------------------------------
 * Buffer binding wrappers
 * -------------------------------------------------------------------------- */

void glBindVertexArray(GLuint array) {
    bhdr_init();
    bhdr_real_gl.glBindVertexArray(array);
    bhdr_shadow_bind_vao(&bhdr_shadow, array);
}

void glBindBuffer(GLenum target, GLuint buffer) {
    bhdr_init();
    bhdr_real_gl.glBindBuffer(target, buffer);
    bhdr_shadow_bind_buffer(&bhdr_shadow, target, buffer);
}

void glBindFramebuffer(GLenum target, GLuint framebuffer) {
    bhdr_init();
    bhdr_real_gl.glBindFramebuffer(target, framebuffer);
    bhdr_shadow_bind_framebuffer(&bhdr_shadow, target, framebuffer);
}

void glFramebufferTexture2D(GLenum target, GLenum attachment, GLenum textarget,
                             GLuint texture, GLint level) {
    bhdr_init();
    if (bhdr_real_gl.glFramebufferTexture2D)
        bhdr_real_gl.glFramebufferTexture2D(target, attachment, textarget, texture, level);
    bhdr_shadow_framebuffer_texture_2d(&bhdr_shadow, target, attachment, texture);
}

/* --------------------------------------------------------------------------
 * Readback pass-throughs (no shadow state to update)
 * -------------------------------------------------------------------------- */

void glReadPixels(GLint x, GLint y, GLsizei width, GLsizei height,
                   GLenum format, GLenum type, void* pixels) {
    bhdr_init();
    bhdr_real_gl.glReadPixels(x, y, width, height, format, type, pixels);
}

void glGetIntegerv(GLenum pname, GLint* data) {
    bhdr_init();
    bhdr_real_gl.glGetIntegerv(pname, data);
}

/* --------------------------------------------------------------------------
 * Debug group wrappers (GL_KHR_debug)
 * -------------------------------------------------------------------------- */

void glPushDebugGroup(GLenum source, GLuint id, GLsizei length, const char* message) {
    bhdr_init();
    if (bhdr_real_gl.glPushDebugGroup)
        bhdr_real_gl.glPushDebugGroup(source, id, length, message);
    bhdr_shadow_push_debug_group(&bhdr_shadow, id, message);
}

void glPopDebugGroup(void) {
    bhdr_init();
    if (bhdr_real_gl.glPopDebugGroup)
        bhdr_real_gl.glPopDebugGroup();
    bhdr_shadow_pop_debug_group(&bhdr_shadow);
}

/* --------------------------------------------------------------------------
 * GLX wrappers
 * -------------------------------------------------------------------------- */

void glXSwapBuffers(Display* dpy, GLXDrawable drawable) {
    bhdr_init();
    bhdr_frame_on_swap();             /* capture before swap (includes draw call data) */
    bhdr_frame_reset_draw_calls();    /* clear per-frame buffer for next frame */
    bhdr_shadow_new_frame(&bhdr_shadow);
    bhdr_real_gl.glXSwapBuffers(dpy, drawable);
}

/* EGL swap path — same shape as glXSwapBuffers. Triggers on chromium /
 * Wayland / Android-style stacks where libEGL is the swap entrypoint. */
unsigned int eglSwapBuffers(void* dpy, void* surface) {
    bhdr_init();
    bhdr_frame_on_swap();
    bhdr_frame_reset_draw_calls();
    bhdr_shadow_new_frame(&bhdr_shadow);
    if (bhdr_real_gl.eglSwapBuffers) {
        return bhdr_real_gl.eglSwapBuffers(dpy, surface);
    }
    return 1;  /* EGL_TRUE */
}

/* --------------------------------------------------------------------------
 * Programmatic frame trigger
 *
 * For offscreen GL contexts (headless-gl, EGL pbuffer, FBO-only pipelines)
 * that never call glXSwapBuffers. Mirrors the body of glXSwapBuffers
 * exactly except for the (omitted) real swap. The host process loads the
 * shim under LD_PRELOAD, dlsym()s this symbol, and calls it once per
 * logical frame.
 * -------------------------------------------------------------------------- */

__attribute__((visibility("default")))
void bhdr_emit_frame(void) {
    bhdr_init();
    bhdr_frame_on_swap();             /* capture: draw calls + framebuffer + IPC notify */
    bhdr_frame_reset_draw_calls();    /* clear per-frame buffer for next frame */
    bhdr_shadow_new_frame(&bhdr_shadow);
}

/* Map function names to our wrapper addresses so that apps using
 * glXGetProcAddress get our interceptors, not the real GL functions. */
static __GLXextFuncPtr bhdr_resolve_wrapper(const char* name) {
    if (!name) return (void*)0;
    /* Draw calls */
    if (strcmp(name, "glDrawArrays") == 0)            return (__GLXextFuncPtr)glDrawArrays;
    if (strcmp(name, "glDrawElements") == 0)           return (__GLXextFuncPtr)glDrawElements;
    if (strcmp(name, "glDrawArraysInstanced") == 0)    return (__GLXextFuncPtr)glDrawArraysInstanced;
    if (strcmp(name, "glDrawElementsInstanced") == 0)  return (__GLXextFuncPtr)glDrawElementsInstanced;
    /* Shader */
    if (strcmp(name, "glUseProgram") == 0)             return (__GLXextFuncPtr)glUseProgram;
    if (strcmp(name, "glUniform1f") == 0)              return (__GLXextFuncPtr)glUniform1f;
    if (strcmp(name, "glUniform3f") == 0)              return (__GLXextFuncPtr)glUniform3f;
    if (strcmp(name, "glUniform4f") == 0)              return (__GLXextFuncPtr)glUniform4f;
    if (strcmp(name, "glUniform1i") == 0)              return (__GLXextFuncPtr)glUniform1i;
    if (strcmp(name, "glUniformMatrix4fv") == 0)       return (__GLXextFuncPtr)glUniformMatrix4fv;
    if (strcmp(name, "glUniformMatrix3fv") == 0)       return (__GLXextFuncPtr)glUniformMatrix3fv;
    /* Textures */
    if (strcmp(name, "glActiveTexture") == 0)          return (__GLXextFuncPtr)glActiveTexture;
    if (strcmp(name, "glBindTexture") == 0)            return (__GLXextFuncPtr)glBindTexture;
    if (strcmp(name, "glTexImage2D") == 0)             return (__GLXextFuncPtr)glTexImage2D;
    /* Clear */
    if (strcmp(name, "glClear") == 0)                  return (__GLXextFuncPtr)glClear;
    /* State */
    if (strcmp(name, "glEnable") == 0)                 return (__GLXextFuncPtr)glEnable;
    if (strcmp(name, "glDisable") == 0)                return (__GLXextFuncPtr)glDisable;
    if (strcmp(name, "glDepthFunc") == 0)              return (__GLXextFuncPtr)glDepthFunc;
    if (strcmp(name, "glDepthMask") == 0)              return (__GLXextFuncPtr)glDepthMask;
    if (strcmp(name, "glBlendFunc") == 0)              return (__GLXextFuncPtr)glBlendFunc;
    if (strcmp(name, "glCullFace") == 0)               return (__GLXextFuncPtr)glCullFace;
    if (strcmp(name, "glFrontFace") == 0)              return (__GLXextFuncPtr)glFrontFace;
    if (strcmp(name, "glViewport") == 0)               return (__GLXextFuncPtr)glViewport;
    if (strcmp(name, "glScissor") == 0)                return (__GLXextFuncPtr)glScissor;
    /* Buffers */
    if (strcmp(name, "glBindVertexArray") == 0)        return (__GLXextFuncPtr)glBindVertexArray;
    if (strcmp(name, "glBindBuffer") == 0)             return (__GLXextFuncPtr)glBindBuffer;
    if (strcmp(name, "glBindFramebuffer") == 0)        return (__GLXextFuncPtr)glBindFramebuffer;
    if (strcmp(name, "glFramebufferTexture2D") == 0)   return (__GLXextFuncPtr)glFramebufferTexture2D;
    /* Readback */
    if (strcmp(name, "glReadPixels") == 0)             return (__GLXextFuncPtr)glReadPixels;
    if (strcmp(name, "glGetIntegerv") == 0)            return (__GLXextFuncPtr)glGetIntegerv;
    /* Debug groups */
    if (strcmp(name, "glPushDebugGroup") == 0) return (__GLXextFuncPtr)glPushDebugGroup;
    if (strcmp(name, "glPopDebugGroup") == 0)  return (__GLXextFuncPtr)glPopDebugGroup;
    return (void*)0;
}

__GLXextFuncPtr glXGetProcAddressARB(const unsigned char* procName) {
    bhdr_init();
    __GLXextFuncPtr wrapper = bhdr_resolve_wrapper((const char*)procName);
    if (wrapper) return wrapper;
    return bhdr_real_gl.glXGetProcAddressARB(procName);
}

/* Also intercept glXGetProcAddress (non-ARB variant) */
__GLXextFuncPtr glXGetProcAddress(const unsigned char* procName) {
    bhdr_init();
    __GLXextFuncPtr wrapper = bhdr_resolve_wrapper((const char*)procName);
    if (wrapper) return wrapper;
    return bhdr_real_gl.glXGetProcAddressARB(procName);
}
