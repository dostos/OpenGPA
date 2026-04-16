// tests/eval/e4_double_negation_cull.c
//
// E4: Double-Negation Culling
//
// Bug: Two errors interact and partially cancel each other out, making the
//      root cause hard to spot by visual inspection alone.
//
//   Error 1: Model matrix has negative X scale (-1) to mirror the mesh.
//            This flips triangle winding from CCW to CW in clip space.
//   Error 2: glFrontFace(GL_CW) is set, ostensibly to "correct" for the
//            mirrored winding -- but GL_CW makes CW the front face, which
//            means the ORIGINAL CCW faces (the mirrored-back faces) are now
//            treated as front faces too.
//
//   The comment in the code says: "GL_CW because right-handed coords" --
//   a plausible-sounding but incorrect justification.
//
//   With cull face enabled (GL_BACK), the combination means some faces that
//   should be visible are culled and some that should be hidden are shown.
//   For a cube: half the faces render inside-out / are missing.
//
//   The real fix: use glFrontFace(GL_CCW) (the default) and let the
//   negative-scale matrix naturally flip winding; OR negate the scale and
//   keep GL_CCW. Not both.
//
// Compile: gcc -lGL -lX11 -o e4_double_negation_cull e4_double_negation_cull.c

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
typedef void   (*PFNGLUNIFORMMATRIX4FVPROC)(GLint, GLsizei, GLboolean, const GLfloat *);
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
    "attribute vec3 aPos;\n"
    "attribute vec3 aColor;\n"
    "uniform mat4 uMVP;\n"
    "varying vec3 vColor;\n"
    "void main() {\n"
    "    gl_Position = uMVP * vec4(aPos, 1.0);\n"
    "    vColor = aColor;\n"
    "}\n";

static const char *frag_src =
    "#version 120\n"
    "varying vec3 vColor;\n"
    "void main() {\n"
    "    gl_FragColor = vec4(vColor, 1.0);\n"
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

// Column-major orthographic projection (simple)
static void ortho_mvp(GLfloat m[16])
{
    memset(m, 0, 16 * sizeof(GLfloat));
    // Scale down so the cube fits in clip space
    m[0]  =  0.5f;
    m[5]  =  0.5f;
    m[10] = -0.5f;
    m[15] =  1.0f;
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
    XStoreName(dpy, win, "E4: Double-Negation Culling");

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
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_CULL_FACE);
    glCullFace(GL_BACK);
    // BUG: GL_CW is set with a comment claiming it matches right-handed coords.
    // Combined with the -X scale in the model matrix below, this produces
    // incorrect culling: faces that should be visible are culled.
    glFrontFace(GL_CW);  // <-- BUG (should be GL_CCW when scale is positive)

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

    GLint locMVP   = glGetUniformLocation(prog, "uMVP");
    GLint locPos   = glGetAttribLocation(prog,  "aPos");
    GLint locColor = glGetAttribLocation(prog,  "aColor");

    // Cube: 6 faces * 2 triangles = 12 tris, 36 vertices (not indexed for clarity)
    // Each vertex: pos(3) + color(3)
    // Winding is CCW when viewed from outside (standard)
#define FACE(ax,ay,az,bx,by,bz,cx,cx2,cz,dx,dy,dz,r,g,b) \
        ax,ay,az,r,g,b,  bx,by,bz,r,g,b,  cx,cx2,cz,r,g,b, \
        ax,ay,az,r,g,b,  cx,cx2,cz,r,g,b, dx,dy,dz,r,g,b
    static const GLfloat verts[] = {
        // front  (+Z)   CCW from front: BL,BR,TR, BL,TR,TL
        -1,-1, 1, 1,0,0,   1,-1, 1, 1,0,0,   1, 1, 1, 1,0,0,
        -1,-1, 1, 1,0,0,   1, 1, 1, 1,0,0,  -1, 1, 1, 1,0,0,
        // back   (-Z)
        -1,-1,-1, 0,1,0,  -1, 1,-1, 0,1,0,   1, 1,-1, 0,1,0,
        -1,-1,-1, 0,1,0,   1, 1,-1, 0,1,0,   1,-1,-1, 0,1,0,
        // left   (-X)
        -1,-1,-1, 0,0,1,  -1,-1, 1, 0,0,1,  -1, 1, 1, 0,0,1,
        -1,-1,-1, 0,0,1,  -1, 1, 1, 0,0,1,  -1, 1,-1, 0,0,1,
        // right  (+X)
         1,-1,-1, 1,1,0,   1, 1,-1, 1,1,0,   1, 1, 1, 1,1,0,
         1,-1,-1, 1,1,0,   1, 1, 1, 1,1,0,   1,-1, 1, 1,1,0,
        // top    (+Y)
        -1, 1,-1, 1,0,1,  -1, 1, 1, 1,0,1,   1, 1, 1, 1,0,1,
        -1, 1,-1, 1,0,1,   1, 1, 1, 1,0,1,   1, 1,-1, 1,0,1,
        // bottom (-Y)
        -1,-1,-1, 0,1,1,   1,-1,-1, 0,1,1,   1,-1, 1, 0,1,1,
        -1,-1,-1, 0,1,1,   1,-1, 1, 0,1,1,  -1,-1, 1, 0,1,1,
    };
#undef FACE

    GLuint vao, vbo;
    glGenVertexArrays(1, &vao);
    glBindVertexArray(vao);
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(verts), verts, GL_STATIC_DRAW);

    GLsizei stride = 6 * sizeof(GLfloat);
    glEnableVertexAttribArray((GLuint)locPos);
    glVertexAttribPointer((GLuint)locPos, 3, GL_FLOAT, GL_FALSE, stride, (void *)0);
    glEnableVertexAttribArray((GLuint)locColor);
    glVertexAttribPointer((GLuint)locColor, 3, GL_FLOAT, GL_FALSE, stride,
                          (void *)(3 * sizeof(GLfloat)));

    // BUG: negative X scale mirrors the cube, flipping winding CCW->CW in clip space
    // Combined with glFrontFace(GL_CW) above, the two errors interact:
    //   - Mirroring makes original-front-faces have CW winding
    //   - GL_CW says CW is front, so they ARE treated as front -> not culled
    //   - But the original-back-faces now have CCW winding -> treated as back -> culled
    //   Net effect: the "front" in world space shows, but it's the mirrored geometry.
    //   Some faces are doubly-wrong and appear inside-out.
    GLfloat mvp[16];
    ortho_mvp(mvp);
    mvp[0] = -mvp[0];  // negative X scale to mirror  <-- BUG (paired with GL_CW)

    for (int frame = 0; frame < 5; frame++) {
        glClearColor(0.2f, 0.2f, 0.2f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        glUseProgram(prog);
        glUniformMatrix4fv(locMVP, 1, GL_FALSE, mvp);
        glBindVertexArray(vao);
        glDrawArrays(GL_TRIANGLES, 0, 36);

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

    printf("e4_double_negation_cull: completed 5 frames\n");
    return 0;
}
