// tests/eval/e1_state_leak.c
//
// E1: State Leak
//
// Bug: glBindTexture is missing before Quad B's draw call.
//      Quad B inherits Quad A's texture (red), so both quads appear red
//      instead of Quad A=red, Quad B=blue.
//
// Compile: gcc -lGL -lX11 -o e1_state_leak e1_state_leak.c

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
typedef void   (*PFNGLUNIFORM1IPROC)(GLint, GLint);
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

// Vertex shader: pass-through with 2D position and texcoord
static const char *vert_src =
    "#version 120\n"
    "attribute vec2 aPos;\n"
    "attribute vec2 aUV;\n"
    "varying vec2 vUV;\n"
    "void main() {\n"
    "    gl_Position = vec4(aPos, 0.0, 1.0);\n"
    "    vUV = aUV;\n"
    "}\n";

// Fragment shader: sample texture
static const char *frag_src =
    "#version 120\n"
    "uniform sampler2D uTex;\n"
    "varying vec2 vUV;\n"
    "void main() {\n"
    "    gl_FragColor = texture2D(uTex, vUV);\n"
    "}\n";

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

// Create a 1x1 solid-color texture
static GLuint make_solid_texture(GLubyte r, GLubyte g, GLubyte b)
{
    GLuint tex;
    glGenTextures(1, &tex);
    glBindTexture(GL_TEXTURE_2D, tex);
    GLubyte px[4] = {r, g, b, 255};
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1, 1, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, px);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    return tex;
}

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
    XStoreName(dpy, win, "E1: State Leak");

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
    LOAD_PROC(PFNGLUNIFORM1IPROC,             glUniform1i)
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

    // Build shader program
    GLuint vs = compile_shader(glCreateShader, glShaderSource, glCompileShader,
                               glGetShaderiv, glGetShaderInfoLog,
                               GL_VERTEX_SHADER, vert_src);
    GLuint fs = compile_shader(glCreateShader, glShaderSource, glCompileShader,
                               glGetShaderiv, glGetShaderInfoLog,
                               GL_FRAGMENT_SHADER, frag_src);
    if (!vs || !fs) return 1;

    GLuint prog = glCreateProgram();
    glAttachShader(prog, vs);
    glAttachShader(prog, fs);
    glLinkProgram(prog);
    {
        GLint ok = 0;
        glGetProgramiv(prog, GL_LINK_STATUS, &ok);
        if (!ok) { fprintf(stderr, "Program link error\n"); return 1; }
    }
    glDeleteShader(vs);
    glDeleteShader(fs);

    GLint texLoc = glGetUniformLocation(prog, "uTex");
    GLint posLoc = glGetAttribLocation(prog,  "aPos");
    GLint uvLoc  = glGetAttribLocation(prog,  "aUV");

    // Textures: tex_red for quad A, tex_blue for quad B
    GLuint tex_red  = make_solid_texture(255, 0, 0);
    GLuint tex_blue = make_solid_texture(0, 0, 255);

    // Quad A: left half  [-1, -0.5] x [-0.8, 0.8]
    // Quad B: right half [0.5,  1 ] x [-0.8, 0.8]
    // Each quad: 2 triangles (6 vertices), interleaved pos(xy)+uv(xy)
    static const GLfloat quad_a[] = {
        -1.0f, -0.8f,  0.0f, 0.0f,
        -0.1f, -0.8f,  1.0f, 0.0f,
        -0.1f,  0.8f,  1.0f, 1.0f,
        -1.0f, -0.8f,  0.0f, 0.0f,
        -0.1f,  0.8f,  1.0f, 1.0f,
        -1.0f,  0.8f,  0.0f, 1.0f,
    };
    static const GLfloat quad_b[] = {
         0.1f, -0.8f,  0.0f, 0.0f,
         1.0f, -0.8f,  1.0f, 0.0f,
         1.0f,  0.8f,  1.0f, 1.0f,
         0.1f, -0.8f,  0.0f, 0.0f,
         1.0f,  0.8f,  1.0f, 1.0f,
         0.1f,  0.8f,  0.0f, 1.0f,
    };

    GLuint vao_a, vbo_a, vao_b, vbo_b;
    glGenVertexArrays(1, &vao_a);
    glBindVertexArray(vao_a);
    glGenBuffers(1, &vbo_a);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_a);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad_a), quad_a, GL_STATIC_DRAW);
    glEnableVertexAttribArray((GLuint)posLoc);
    glVertexAttribPointer((GLuint)posLoc, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat), (void *)0);
    glEnableVertexAttribArray((GLuint)uvLoc);
    glVertexAttribPointer((GLuint)uvLoc, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat), (void *)(2 * sizeof(GLfloat)));

    glGenVertexArrays(1, &vao_b);
    glBindVertexArray(vao_b);
    glGenBuffers(1, &vbo_b);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_b);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad_b), quad_b, GL_STATIC_DRAW);
    glEnableVertexAttribArray((GLuint)posLoc);
    glVertexAttribPointer((GLuint)posLoc, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat), (void *)0);
    glEnableVertexAttribArray((GLuint)uvLoc);
    glVertexAttribPointer((GLuint)uvLoc, 2, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat), (void *)(2 * sizeof(GLfloat)));

    for (int frame = 0; frame < 5; frame++) {
        glClearColor(0.15f, 0.15f, 0.15f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        glUseProgram(prog);
        glActiveTexture(GL_TEXTURE0);
        glUniform1i(texLoc, 0);

        // Draw Quad A: bind red texture then draw
        glBindTexture(GL_TEXTURE_2D, tex_red);
        glBindVertexArray(vao_a);
        glDrawArrays(GL_TRIANGLES, 0, 6);

        // Draw Quad B: BUG - glBindTexture(GL_TEXTURE_2D, tex_blue) is missing!
        // tex_red is still bound, so Quad B renders red instead of blue.
        /* glBindTexture(GL_TEXTURE_2D, tex_blue); */  // <-- intentionally omitted
        glBindVertexArray(vao_b);
        glDrawArrays(GL_TRIANGLES, 0, 6);

        glXSwapBuffers(dpy, win);
    }

    glDeleteVertexArrays(1, &vao_a);
    glDeleteBuffers(1, &vbo_a);
    glDeleteVertexArrays(1, &vao_b);
    glDeleteBuffers(1, &vbo_b);
    glDeleteTextures(1, &tex_red);
    glDeleteTextures(1, &tex_blue);
    glDeleteProgram(prog);

    glXMakeCurrent(dpy, None, NULL);
    glXDestroyContext(dpy, glc);
    XDestroyWindow(dpy, win);
    XFreeColormap(dpy, swa.colormap);
    XFree(vi);
    XCloseDisplay(dpy);

    printf("e1_state_leak: completed 5 frames\n");
    return 0;
}
