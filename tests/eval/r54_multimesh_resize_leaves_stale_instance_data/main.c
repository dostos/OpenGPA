// SOURCE: https://github.com/godotengine/godot/issues/75485
//
// Godot consumer pattern: a MultiMesh whose instance_count is changed at
// runtime. Internally Godot reuses the per-instance VBO across instance-
// count changes; when the count grows back from a smaller value, the
// buffer region [old_count..new_count) keeps whatever GPU bytes were
// last there. The reporter saw this as "strange data appears in the
// buffer" with instances rendered at unintended positions.
//
// This reproduction mirrors the buffer lifecycle:
//   1. Allocate an instance VBO sized for N=8 with sane transforms.
//   2. "Shrink" by drawing only 4 instances for a frame.
//   3. The user re-grows the MultiMesh to 8 and re-uploads instances
//      [0..3] only, assuming [4..7] will be reset. They are not — the
//      previous frame's transforms persist for instances 4..7.
//   4. Draw all 8 instances. Instances 4..7 render at their stale
//      positions, not where the user just placed them.
#include <GL/gl.h>
#include <GL/glx.h>
#include <X11/Xlib.h>
#include <stdio.h>
#include <string.h>

#define GLX_CONTEXT_MAJOR_VERSION_ARB 0x2091
#define GLX_CONTEXT_MINOR_VERSION_ARB 0x2092
#define GLX_CONTEXT_PROFILE_MASK_ARB  0x9126
#define GLX_CONTEXT_CORE_PROFILE_BIT_ARB 0x00000001

typedef GLuint (*PFNCS)(GLenum);
typedef void   (*PFNSS)(GLuint, GLsizei, const char* const*, const GLint*);
typedef void   (*PFNCMP)(GLuint);
typedef GLuint (*PFNCP)(void);
typedef void   (*PFNAS)(GLuint, GLuint);
typedef void   (*PFNLP)(GLuint);
typedef void   (*PFNUP)(GLuint);
typedef void   (*PFNGEN)(GLsizei, GLuint*);
typedef void   (*PFNBIND)(GLuint);
typedef void   (*PFNBINDB)(GLenum, GLuint);
typedef void   (*PFNBD)(GLenum, GLsizeiptr, const void*, GLenum);
typedef void   (*PFNBSD)(GLenum, GLintptr, GLsizeiptr, const void*);
typedef void   (*PFNVAP)(GLuint, GLint, GLenum, GLboolean, GLsizei, const void*);
typedef void   (*PFNEVA)(GLuint);
typedef void   (*PFNDIV)(GLuint, GLuint);
typedef void   (*PFNDAI)(GLenum, GLint, GLsizei, GLsizei);
typedef GLint  (*PFNGUL)(GLuint, const char*);
typedef void   (*PFNU2F)(GLint, GLfloat, GLfloat);
typedef GLXContext (*PFNCCAA)(Display*, GLXFBConfig, GLXContext, Bool, const int*);

#define GP(T,N) (T)glXGetProcAddressARB((const GLubyte*)N)

static const char* VS =
"#version 330 core\n"
"layout(location=0) in vec2 a_pos;\n"
"layout(location=1) in vec2 a_offset;\n"
"layout(location=2) in vec3 a_color;\n"
"uniform vec2 u_viewport;\n"
"out vec3 v_color;\n"
"void main(){\n"
"  vec2 p = a_pos + a_offset;\n"
"  gl_Position = vec4(p / u_viewport * 2.0 - 1.0, 0.0, 1.0);\n"
"  v_color = a_color;\n"
"}\n";
static const char* FS =
"#version 330 core\n"
"in vec3 v_color;\n"
"out vec4 o;\n"
"void main(){ o = vec4(v_color, 1.0); }\n";

#define W 512
#define H 256
#define INST_STRIDE (5*sizeof(float))   /* offset.xy, color.rgb */

int main(void){
    Display* dpy = XOpenDisplay(NULL);
    if(!dpy){ fprintf(stderr,"no display\n"); return 1; }
    int attrs[] = {
        GLX_X_RENDERABLE, True, GLX_DRAWABLE_TYPE, GLX_WINDOW_BIT,
        GLX_RENDER_TYPE, GLX_RGBA_BIT,
        GLX_RED_SIZE, 8, GLX_GREEN_SIZE, 8, GLX_BLUE_SIZE, 8, GLX_ALPHA_SIZE, 8,
        GLX_DEPTH_SIZE, 24, GLX_DOUBLEBUFFER, True, None
    };
    int n=0;
    GLXFBConfig* fbc = glXChooseFBConfig(dpy, DefaultScreen(dpy), attrs, &n);
    if(!fbc||!n){ fprintf(stderr,"no fbc\n"); return 1; }
    XVisualInfo* vi = glXGetVisualFromFBConfig(dpy, fbc[0]);
    Window root = RootWindow(dpy, vi->screen);
    XSetWindowAttributes swa = {0};
    swa.colormap = XCreateColormap(dpy, root, vi->visual, AllocNone);
    Window win = XCreateWindow(dpy, root, 0,0,W,H,0,vi->depth,
                               InputOutput, vi->visual, CWColormap, &swa);
    XMapWindow(dpy, win);
    PFNCCAA create_ctx = GP(PFNCCAA, "glXCreateContextAttribsARB");
    int ca[] = {
        GLX_CONTEXT_MAJOR_VERSION_ARB, 3,
        GLX_CONTEXT_MINOR_VERSION_ARB, 3,
        GLX_CONTEXT_PROFILE_MASK_ARB, GLX_CONTEXT_CORE_PROFILE_BIT_ARB, 0
    };
    GLXContext ctx = create_ctx(dpy, fbc[0], 0, True, ca);
    glXMakeCurrent(dpy, win, ctx);

    PFNCS  cs = GP(PFNCS, "glCreateShader");
    PFNSS  ss = GP(PFNSS, "glShaderSource");
    PFNCMP cmp= GP(PFNCMP,"glCompileShader");
    PFNCP  cp = GP(PFNCP, "glCreateProgram");
    PFNAS  as = GP(PFNAS, "glAttachShader");
    PFNLP  lp = GP(PFNLP, "glLinkProgram");
    PFNUP  up = GP(PFNUP, "glUseProgram");
    PFNGEN gva= GP(PFNGEN,"glGenVertexArrays");
    PFNBIND bva=GP(PFNBIND,"glBindVertexArray");
    PFNGEN gb = GP(PFNGEN,"glGenBuffers");
    PFNBINDB bb=GP(PFNBINDB,"glBindBuffer");
    PFNBD  bd = GP(PFNBD, "glBufferData");
    PFNBSD bsd= GP(PFNBSD,"glBufferSubData");
    PFNVAP vap= GP(PFNVAP,"glVertexAttribPointer");
    PFNEVA eva= GP(PFNEVA,"glEnableVertexAttribArray");
    PFNDIV div= GP(PFNDIV,"glVertexAttribDivisor");
    PFNDAI dai= GP(PFNDAI,"glDrawArraysInstanced");
    PFNGUL gul= GP(PFNGUL,"glGetUniformLocation");
    PFNU2F u2f= GP(PFNU2F,"glUniform2f");

    GLuint vs = cs(GL_VERTEX_SHADER); ss(vs,1,&VS,NULL); cmp(vs);
    GLuint fs = cs(GL_FRAGMENT_SHADER); ss(fs,1,&FS,NULL); cmp(fs);
    GLuint prog = cp(); as(prog,vs); as(prog,fs); lp(prog);

    GLuint vao; gva(1,&vao); bva(vao);

    /* Per-vertex 32×32 quad. */
    float quad[] = { 0,0, 32,0, 0,32,  0,32, 32,0, 32,32 };
    GLuint vbo; gb(1,&vbo); bb(GL_ARRAY_BUFFER, vbo);
    bd(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    vap(0,2,GL_FLOAT,GL_FALSE,2*sizeof(float),(void*)0);
    eva(0);

    /* Stage 1: MultiMesh originally has 8 instances laid out across the
       viewport. */
    float initial_xy_color[8 * 5] = {
         32.0f,  64.0f, 0.6f, 0.0f, 0.6f,   /* purple, will be overwritten */
        128.0f,  64.0f, 0.6f, 0.0f, 0.6f,
        224.0f,  64.0f, 0.6f, 0.0f, 0.6f,
        320.0f,  64.0f, 0.6f, 0.0f, 0.6f,
        416.0f,  64.0f, 0.0f, 0.6f, 0.6f,   /* cyan — these four are the
                                               "stale" instances 4..7 */
         32.0f, 192.0f, 0.0f, 0.6f, 0.6f,   /* off-screen for x>W ignored;
                                               y=192 is below the row */
        128.0f, 192.0f, 0.0f, 0.6f, 0.6f,
        224.0f, 192.0f, 0.0f, 0.6f, 0.6f,
    };

    GLuint ibo; gb(1,&ibo); bb(GL_ARRAY_BUFFER, ibo);
    bd(GL_ARRAY_BUFFER, 8 * INST_STRIDE, initial_xy_color, GL_DYNAMIC_DRAW);

    vap(1,2,GL_FLOAT,GL_FALSE,INST_STRIDE,(void*)0);
    eva(1); div(1,1);
    vap(2,3,GL_FLOAT,GL_FALSE,INST_STRIDE,(void*)(2*sizeof(float)));
    eva(2); div(2,1);

    /* Stage 2: user "shrinks" the MultiMesh to 4 — Godot leaves the VBO
       sized for 8, only the active count changes. (Nothing to do at the
       GL layer here; we just don't draw the bottom 4 yet.) */

    /* Stage 3: user "grows" back to 8 and re-populates instances [0..3]
       with the new green positions, expecting [4..7] to be reset. The
       MultiMesh API only writes the first four; the rest of the VBO
       still holds the cyan stale rows from stage 1. */
    float new_first_four[4 * 5] = {
         32.0f, 128.0f, 0.0f, 0.8f, 0.0f,
        128.0f, 128.0f, 0.0f, 0.8f, 0.0f,
        224.0f, 128.0f, 0.0f, 0.8f, 0.0f,
        320.0f, 128.0f, 0.0f, 0.8f, 0.0f,
    };
    bsd(GL_ARRAY_BUFFER, 0, sizeof(new_first_four), new_first_four);

    /* Stage 4: draw all 8 instances. */
    glViewport(0,0,W,H);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);
    up(prog);
    u2f(gul(prog,"u_viewport"), (float)W, (float)H);
    dai(GL_TRIANGLES, 0, 6, 8);

    glXSwapBuffers(dpy, win);
    glFinish();

    /* Stale instance 4 renders at GL coords (416..448, 64..96) — its
       centre is (432, 80). glReadPixels uses GL bottom-left origin. */
    unsigned char px[4] = {0};
    glReadPixels(432, 80, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
    fprintf(stderr,
            "instance-4 centre = %u,%u,%u,%u (expected black 0,0,0; "
            "stale cyan ≈ 0,153,153 means bug)\n",
            px[0], px[1], px[2], px[3]);

    glXMakeCurrent(dpy, None, NULL);
    glXDestroyContext(dpy, ctx);
    XDestroyWindow(dpy, win);
    XCloseDisplay(dpy);
    return 0;
}
