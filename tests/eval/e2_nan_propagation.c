// tests/eval/e2_nan_propagation.c
//
// E2: NaN Propagation
//
// Bug: Model matrix has scale(1, 1, 0) — zero Z scale — making it singular.
//      The fragment shader computes the normal matrix as transpose(inverse(model)).
//      inverse() of a singular matrix produces Inf values; multiplying Inf by
//      zero produces NaN. The dot product with the light direction becomes NaN,
//      and the clamp(NaN, 0, 1) evaluates to 0, so the lit face appears black.
//
// Compile: gcc -lGL -lX11 -lm -o e2_nan_propagation e2_nan_propagation.c

#include <X11/Xlib.h>
#include <GL/gl.h>
#include <GL/glx.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

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
typedef void   (*PFNGLUNIFORMMATRIX4FVPROC)(GLint, GLsizei, GLboolean, const GLfloat *);
typedef void   (*PFNGLUNIFORMMATRIX3FVPROC)(GLint, GLsizei, GLboolean, const GLfloat *);
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

// Vertex shader: transforms positions and normals, passes to fragment shader
static const char *vert_src =
    "#version 120\n"
    "attribute vec3 aPos;\n"
    "attribute vec3 aNormal;\n"
    "uniform mat4 uModel;\n"
    "uniform mat4 uMVP;\n"
    "uniform mat3 uNormalMatrix;\n"  // transpose(inverse(model)) -- contains Inf/NaN
    "varying vec3 vNormal;\n"
    "varying vec3 vPos;\n"
    "void main() {\n"
    "    gl_Position = uMVP * vec4(aPos, 1.0);\n"
    "    vNormal = uNormalMatrix * aNormal;\n"  // NaN propagates here
    "    vPos    = vec3(uModel * vec4(aPos, 1.0));\n"
    "}\n";

// Fragment shader: simple diffuse lighting
static const char *frag_src =
    "#version 120\n"
    "varying vec3 vNormal;\n"
    "varying vec3 vPos;\n"
    "void main() {\n"
    "    vec3 lightDir = normalize(vec3(1.0, 1.0, 2.0));\n"
    "    vec3 n = normalize(vNormal);\n"
    "    float diff = max(dot(n, lightDir), 0.0);\n"  // NaN -> 0 -> black
    "    gl_FragColor = vec4(vec3(0.8) * diff + vec3(0.05), 1.0);\n"
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

// Column-major 4x4 identity
static void mat4_identity(GLfloat m[16])
{
    memset(m, 0, 16 * sizeof(GLfloat));
    m[0] = m[5] = m[10] = m[15] = 1.0f;
}

// Build mat3 normal matrix from mat4 model (transpose-inverse, computed on CPU).
// With scale(1,1,0), det=0, inverse is ill-defined -> entries become Inf.
static void compute_normal_matrix(const GLfloat m[16], GLfloat nm[9])
{
    // Extract upper-left 3x3 from column-major mat4
    float a = m[0], b = m[4], c = m[8];
    float d = m[1], e = m[5], f = m[9];
    float g = m[2], h = m[6], k = m[10];

    float det = a*(e*k - f*h) - b*(d*k - f*g) + c*(d*h - e*g);
    // When scale Z=0, det=0; 1/det = Inf
    float inv_det = 1.0f / det;

    // Inverse then transpose (= adjugate / det, then transpose)
    // Result stored column-major for GL
    nm[0] = (e*k - f*h) * inv_det;
    nm[1] = (c*h - b*k) * inv_det;
    nm[2] = (b*f - c*e) * inv_det;

    nm[3] = (f*g - d*k) * inv_det;
    nm[4] = (a*k - c*g) * inv_det;
    nm[5] = (c*d - a*f) * inv_det;

    nm[6] = (d*h - e*g) * inv_det;
    nm[7] = (b*g - a*h) * inv_det;
    nm[8] = (a*e - b*d) * inv_det;
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
    XStoreName(dpy, win, "E2: NaN Propagation");

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
    LOAD_PROC(PFNGLUNIFORMMATRIX4FVPROC,      glUniformMatrix4fv)
    LOAD_PROC(PFNGLUNIFORMMATRIX3FVPROC,      glUniformMatrix3fv)
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
    glEnable(GL_DEPTH_TEST);

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

    GLint locModel  = glGetUniformLocation(prog, "uModel");
    GLint locMVP    = glGetUniformLocation(prog, "uMVP");
    GLint locNM     = glGetUniformLocation(prog, "uNormalMatrix");
    GLint locPos    = glGetAttribLocation(prog,  "aPos");
    GLint locNormal = glGetAttribLocation(prog,  "aNormal");

    // Front face of a quad: pos(3) + normal(3) interleaved, 6 vertices
    static const GLfloat verts[] = {
        // pos             normal (front face +Z)
        -0.5f, -0.5f, 0.0f,   0.0f, 0.0f, 1.0f,
         0.5f, -0.5f, 0.0f,   0.0f, 0.0f, 1.0f,
         0.5f,  0.5f, 0.0f,   0.0f, 0.0f, 1.0f,
        -0.5f, -0.5f, 0.0f,   0.0f, 0.0f, 1.0f,
         0.5f,  0.5f, 0.0f,   0.0f, 0.0f, 1.0f,
        -0.5f,  0.5f, 0.0f,   0.0f, 0.0f, 1.0f,
    };

    GLuint vao, vbo;
    glGenVertexArrays(1, &vao);
    glBindVertexArray(vao);
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(verts), verts, GL_STATIC_DRAW);

    GLsizei stride = 6 * sizeof(GLfloat);
    glEnableVertexAttribArray((GLuint)locPos);
    glVertexAttribPointer((GLuint)locPos, 3, GL_FLOAT, GL_FALSE, stride, (void *)0);
    glEnableVertexAttribArray((GLuint)locNormal);
    glVertexAttribPointer((GLuint)locNormal, 3, GL_FLOAT, GL_FALSE, stride,
                          (void *)(3 * sizeof(GLfloat)));

    // BUG: model matrix uses scale(1, 1, 0) -- intended for flat shadow projection
    // This makes the matrix singular, so inverse() produces Inf, and normal matrix has NaN.
    GLfloat model[16];
    mat4_identity(model);
    model[10] = 0.0f;  // Z scale = 0  <-- the bug

    GLfloat mvp[16];
    mat4_identity(mvp);  // simple orthographic for this demo

    GLfloat nm[9];
    compute_normal_matrix(model, nm);

    for (int frame = 0; frame < 5; frame++) {
        glClearColor(0.2f, 0.2f, 0.3f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        glUseProgram(prog);
        glUniformMatrix4fv(locModel, 1, GL_FALSE, model);
        glUniformMatrix4fv(locMVP,   1, GL_FALSE, mvp);
        // Upload normal matrix that contains Inf/NaN due to singular model
        glUniformMatrix3fv(locNM, 1, GL_FALSE, nm);

        glBindVertexArray(vao);
        glDrawArrays(GL_TRIANGLES, 0, 6);

        glXSwapBuffers(dpy, win);
    }

    glDeleteVertexArrays(1, &vao);
    glDeleteBuffers(1, &vbo);
    glDeleteProgram(prog);

    glXMakeCurrent(dpy, None, NULL);
    glXDestroyContext(dpy, glc);
    XDestroyWindow(dpy, win);
    XFreeColormap(dpy, swa.colormap);
    XFree(vi);
    XCloseDisplay(dpy);

    printf("e2_nan_propagation: completed 5 frames\n");
    return 0;
}
