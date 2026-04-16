// tests/eval/e5_uniform_collision.c
//
// E5: Uniform Location Collision
//
// Bug: Two materials share a uniform-location cache keyed by a material enum.
//      The enum was reordered (MAT_BLUE was 1, is now 0; MAT_RED was 0, is now 1),
//      but the cache array was not invalidated.  At initialisation the cache is
//      filled in enum order: cache[0] = query("uColor") for the first material
//      that happens to run, etc.  After the reorder, material A (red) reads
//      cache[MAT_RED=1] which holds the location that was cached for the OLD
//      MAT_RED=0 slot — i.e. it uses material B's cached location.
//
//      Concretely: both objects end up with the same uniform value (whichever
//      was written last), so one object shows the wrong color.
//
//      The simulation below models this with two programs (one per material)
//      and a cache array indexed by the (now-wrong) enum value.
//
// Compile: gcc -lGL -lX11 -o e5_uniform_collision e5_uniform_collision.c

#include <X11/Xlib.h>
#include <GL/gl.h>
#include <GL/glx.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef GLuint (*PFNGLCREATESHADERPROC)(GLenum);
typedef void   (*PFNGLSHADERSOURCEPROC)(GLuint, GLsizei, const GLchar *const*, const GLint *);
typedef void   (*PFNGLCOMPILESHADERPROC)(GLuint);
typedef void   (*PFNGLGETSHADERIVPROC)(GLuint, GLenum, GLint *);
typedef void   (*PFNGLGETSHADERINFOLOGPROC)(GLuint, GLsizei, GLsizei *, GLchar *);
typedef GLuint (*PFNGLCREATEPROGRAMPROC)(void);
typedef void   (*PFNGLATTACHSHADERPROC)(GLuint, GLuint);
typedef void   (*PFNGLLINKPROGRAMPROC)(GLuint);
typedef void   (*PFNGLGETPROGRAMIVPROC)(GLuint, GLenum, GLint *);
typedef void   (*PFNGLUSEPROGRAMPROC)(GLuint);
typedef GLint  (*PFNGLGETUNIFORMLOCATIONPROC)(GLuint, const GLchar *);
typedef void   (*PFNGLUNIFORM4FPROC)(GLint, GLfloat, GLfloat, GLfloat, GLfloat);
typedef void   (*PFNGLGENBUFFERSPROC)(GLsizei, GLuint *);
typedef void   (*PFNGLBINDBUFFERPROC)(GLenum, GLuint);
typedef void   (*PFNGLBUFFERDATAPROC)(GLenum, GLsizeiptr, const void *, GLenum);
typedef void   (*PFNGLGENVERTEXARRAYSPROC)(GLsizei, GLuint *);
typedef void   (*PFNGLBINDVERTEXARRAYPROC)(GLuint);
typedef void   (*PFNGLENABLEVERTEXATTRIBARRAYPROC)(GLuint);
typedef void   (*PFNGLVERTEXATTRIBPOINTERPROC)(GLuint, GLint, GLenum, GLboolean, GLsizei, const void *);
typedef GLint  (*PFNGLGETATTRIBLOCATIONPROC)(GLuint, const GLchar *);
typedef void   (*PFNGLDELETESHADERPROC)(GLuint);
typedef void   (*PFNGLDELETEPROGRAMPROC)(GLuint);
typedef void   (*PFNGLDELETEBUFFERSPROC)(GLsizei, const GLuint *);
typedef void   (*PFNGLDELETEVERTEXARRAYSPROC)(GLsizei, const GLuint *);

#define LOAD_PROC(type, name) \
    type name = (type)glXGetProcAddress((const GLubyte *)#name); \
    if (!name) { fprintf(stderr, "Cannot resolve " #name "\n"); return 1; }

static const char *vert_src =
    "#version 120\n"
    "attribute vec2 aPos;\n"
    "void main() { gl_Position = vec4(aPos, 0.0, 1.0); }\n";

static const char *frag_src =
    "#version 120\n"
    "uniform vec4 uColor;\n"
    "void main() { gl_FragColor = uColor; }\n";

static GLuint compile_shader(
    PFNGLCREATESHADERPROC     glCreateShader,
    PFNGLSHADERSOURCEPROC     glShaderSource,
    PFNGLCOMPILESHADERPROC    glCompileShader,
    PFNGLGETSHADERIVPROC      glGetShaderiv,
    PFNGLGETSHADERINFOLOGPROC glGetShaderInfoLog,
    GLenum type, const char *src)
{
    GLuint id = glCreateShader(type);
    glShaderSource(id, 1, &src, NULL);
    glCompileShader(id);
    GLint ok = 0;
    glGetShaderiv(id, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[512];
        glGetShaderInfoLog(id, sizeof(log), NULL, log);
        fprintf(stderr, "Shader compile error: %s\n", log);
        return 0;
    }
    return id;
}

static GLuint build_program(
    PFNGLCREATESHADERPROC     glCreateShader,
    PFNGLSHADERSOURCEPROC     glShaderSource,
    PFNGLCOMPILESHADERPROC    glCompileShader,
    PFNGLGETSHADERIVPROC      glGetShaderiv,
    PFNGLGETSHADERINFOLOGPROC glGetShaderInfoLog,
    PFNGLCREATEPROGRAMPROC    glCreateProgram,
    PFNGLATTACHSHADERPROC     glAttachShader,
    PFNGLLINKPROGRAMPROC      glLinkProgram,
    PFNGLGETPROGRAMIVPROC     glGetProgramiv,
    PFNGLDELETESHADERPROC     glDeleteShader)
{
    GLuint vs = compile_shader(glCreateShader, glShaderSource, glCompileShader,
                               glGetShaderiv, glGetShaderInfoLog,
                               GL_VERTEX_SHADER, vert_src);
    GLuint fs = compile_shader(glCreateShader, glShaderSource, glCompileShader,
                               glGetShaderiv, glGetShaderInfoLog,
                               GL_FRAGMENT_SHADER, frag_src);
    if (!vs || !fs) return 0;
    GLuint p = glCreateProgram();
    glAttachShader(p, vs);
    glAttachShader(p, fs);
    glLinkProgram(p);
    GLint ok = 0;
    glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) { fprintf(stderr, "Program link error\n"); return 0; }
    glDeleteShader(vs);
    glDeleteShader(fs);
    return p;
}

// --------------------------------------------------------------------------
// Material enum -- REORDERED since the cache was originally populated.
//
// Original order (when cache was filled):
//   MAT_RED  = 0
//   MAT_BLUE = 1
//
// New order (after a refactor):
//   MAT_BLUE = 0   <-- moved to 0
//   MAT_RED  = 1   <-- moved to 1
//
// The uniform-location cache was NOT cleared after the reorder.
// --------------------------------------------------------------------------
typedef enum {
    MAT_BLUE = 0,   // was MAT_RED=0 before reorder
    MAT_RED  = 1,   // was MAT_BLUE=1 before reorder
    MAT_COUNT
} MaterialID;

int main(void)
{
    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) { fprintf(stderr, "Cannot open X display\n"); return 1; }

    int attrs[] = { GLX_RGBA, GLX_DEPTH_SIZE, 24, GLX_DOUBLEBUFFER, None };
    XVisualInfo *vi = glXChooseVisual(dpy, 0, attrs);
    if (!vi) { fprintf(stderr, "No suitable GLX visual\n"); XCloseDisplay(dpy); return 1; }

    Window root = DefaultRootWindow(dpy);
    XSetWindowAttributes swa;
    memset(&swa, 0, sizeof(swa));
    swa.colormap   = XCreateColormap(dpy, root, vi->visual, AllocNone);
    swa.event_mask = ExposureMask;
    Window win = XCreateWindow(dpy, root, 0, 0, 400, 300, 0, vi->depth,
                               InputOutput, vi->visual, CWColormap | CWEventMask, &swa);
    XMapWindow(dpy, win);
    XStoreName(dpy, win, "E5: Uniform Collision");

    GLXContext glc = glXCreateContext(dpy, vi, NULL, GL_TRUE);
    if (!glc) { fprintf(stderr, "Cannot create GL context\n"); return 1; }
    glXMakeCurrent(dpy, win, glc);

    LOAD_PROC(PFNGLCREATESHADERPROC,          glCreateShader)
    LOAD_PROC(PFNGLSHADERSOURCEPROC,          glShaderSource)
    LOAD_PROC(PFNGLCOMPILESHADERPROC,         glCompileShader)
    LOAD_PROC(PFNGLGETSHADERIVPROC,           glGetShaderiv)
    LOAD_PROC(PFNGLGETSHADERINFOLOGPROC,      glGetShaderInfoLog)
    LOAD_PROC(PFNGLCREATEPROGRAMPROC,         glCreateProgram)
    LOAD_PROC(PFNGLATTACHSHADERPROC,          glAttachShader)
    LOAD_PROC(PFNGLLINKPROGRAMPROC,           glLinkProgram)
    LOAD_PROC(PFNGLGETPROGRAMIVPROC,          glGetProgramiv)
    LOAD_PROC(PFNGLUSEPROGRAMPROC,            glUseProgram)
    LOAD_PROC(PFNGLGETUNIFORMLOCATIONPROC,    glGetUniformLocation)
    LOAD_PROC(PFNGLUNIFORM4FPROC,             glUniform4f)
    LOAD_PROC(PFNGLGENBUFFERSPROC,            glGenBuffers)
    LOAD_PROC(PFNGLBINDBUFFERPROC,            glBindBuffer)
    LOAD_PROC(PFNGLBUFFERDATAPROC,            glBufferData)
    LOAD_PROC(PFNGLGENVERTEXARRAYSPROC,       glGenVertexArrays)
    LOAD_PROC(PFNGLBINDVERTEXARRAYPROC,       glBindVertexArray)
    LOAD_PROC(PFNGLENABLEVERTEXATTRIBARRAYPROC, glEnableVertexAttribArray)
    LOAD_PROC(PFNGLVERTEXATTRIBPOINTERPROC,   glVertexAttribPointer)
    LOAD_PROC(PFNGLGETATTRIBLOCATIONPROC,     glGetAttribLocation)
    LOAD_PROC(PFNGLDELETESHADERPROC,          glDeleteShader)
    LOAD_PROC(PFNGLDELETEPROGRAMPROC,         glDeleteProgram)
    LOAD_PROC(PFNGLDELETEBUFFERSPROC,         glDeleteBuffers)
    LOAD_PROC(PFNGLDELETEVERTEXARRAYSPROC,    glDeleteVertexArrays)

    glViewport(0, 0, 400, 300);

    // Build two programs (same shader, but separate GL objects)
    GLuint prog[MAT_COUNT];
    prog[MAT_RED]  = build_program(glCreateShader, glShaderSource, glCompileShader,
                                   glGetShaderiv, glGetShaderInfoLog,
                                   glCreateProgram, glAttachShader, glLinkProgram,
                                   glGetProgramiv, glDeleteShader);
    prog[MAT_BLUE] = build_program(glCreateShader, glShaderSource, glCompileShader,
                                   glGetShaderiv, glGetShaderInfoLog,
                                   glCreateProgram, glAttachShader, glLinkProgram,
                                   glGetProgramiv, glDeleteShader);
    if (!prog[MAT_RED] || !prog[MAT_BLUE]) return 1;

    // BUG: uniform location cache populated using the OLD enum order.
    // Simulated by filling cache[0] and cache[1] in the ORIGINAL order
    // (MAT_RED=0, MAT_BLUE=1) but reading with the NEW enum values
    // (MAT_BLUE=0, MAT_RED=1).
    //
    // In the original code this would have been:
    //   for (int i = 0; i < MAT_COUNT; i++)
    //       color_loc_cache[i] = glGetUniformLocation(prog[i], "uColor");
    // ... then enum was reordered without invalidating the cache.
    //
    // We simulate the stale cache directly:
    GLint color_loc_cache[MAT_COUNT];
    // Cache was filled when MAT_RED=0, MAT_BLUE=1:
    color_loc_cache[0] = glGetUniformLocation(prog[MAT_RED],  "uColor"); // old slot 0 = RED
    color_loc_cache[1] = glGetUniformLocation(prog[MAT_BLUE], "uColor"); // old slot 1 = BLUE
    // Now with new enum: MAT_BLUE=0, MAT_RED=1
    // color_loc_cache[MAT_BLUE=0] actually holds RED's location
    // color_loc_cache[MAT_RED=1]  actually holds BLUE's location
    // -> both objects render with swapped/wrong uniform values

    GLint posLoc = glGetAttribLocation(prog[MAT_RED], "aPos");

    // Left quad (should be red)
    static const GLfloat quad_left[] = {
        -1.0f, -0.8f,  -0.1f, -0.8f,  -0.1f,  0.8f,
        -1.0f, -0.8f,  -0.1f,  0.8f,  -1.0f,  0.8f,
    };
    // Right quad (should be blue)
    static const GLfloat quad_right[] = {
         0.1f, -0.8f,   1.0f, -0.8f,   1.0f,  0.8f,
         0.1f, -0.8f,   1.0f,  0.8f,   0.1f,  0.8f,
    };

    GLuint vao[2], vbo[2];
    glGenVertexArrays(2, vao);
    glGenBuffers(2, vbo);

    glBindVertexArray(vao[0]);
    glBindBuffer(GL_ARRAY_BUFFER, vbo[0]);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad_left), quad_left, GL_STATIC_DRAW);
    glEnableVertexAttribArray((GLuint)posLoc);
    glVertexAttribPointer((GLuint)posLoc, 2, GL_FLOAT, GL_FALSE,
                          2 * sizeof(GLfloat), (void *)0);

    glBindVertexArray(vao[1]);
    glBindBuffer(GL_ARRAY_BUFFER, vbo[1]);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad_right), quad_right, GL_STATIC_DRAW);
    glEnableVertexAttribArray((GLuint)posLoc);
    glVertexAttribPointer((GLuint)posLoc, 2, GL_FLOAT, GL_FALSE,
                          2 * sizeof(GLfloat), (void *)0);

    for (int frame = 0; frame < 5; frame++) {
        glClearColor(0.15f, 0.15f, 0.15f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        // Draw left quad as MAT_RED -- but cache[MAT_RED=1] holds BLUE's location
        glUseProgram(prog[MAT_RED]);
        glUniform4f(color_loc_cache[MAT_RED],  1.0f, 0.0f, 0.0f, 1.0f); // wants red
        glBindVertexArray(vao[0]);
        glDrawArrays(GL_TRIANGLES, 0, 6);

        // Draw right quad as MAT_BLUE -- but cache[MAT_BLUE=0] holds RED's location
        glUseProgram(prog[MAT_BLUE]);
        glUniform4f(color_loc_cache[MAT_BLUE], 0.0f, 0.0f, 1.0f, 1.0f); // wants blue
        glBindVertexArray(vao[1]);
        glDrawArrays(GL_TRIANGLES, 0, 6);

        glXSwapBuffers(dpy, win);
    }

    glDeleteVertexArrays(2, vao);
    glDeleteBuffers(2, vbo);
    glDeleteProgram(prog[MAT_RED]);
    glDeleteProgram(prog[MAT_BLUE]);

    glXMakeCurrent(dpy, None, NULL);
    glXDestroyContext(dpy, glc);
    XDestroyWindow(dpy, win);
    XFreeColormap(dpy, swa.colormap);
    XFree(vi);
    XCloseDisplay(dpy);

    printf("e5_uniform_collision: completed 5 frames\n");
    return 0;
}
