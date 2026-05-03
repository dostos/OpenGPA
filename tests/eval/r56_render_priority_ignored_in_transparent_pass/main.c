// SOURCE: https://github.com/godotengine/godot/issues/34177
//
// Godot consumer pattern: a `MeshInstance3D` has a base material and a
// `next_pass` outline material with `render_priority = 1`. The user
// expects render_priority to make the outline draw last so it renders
// on top of the base mesh. When the materials are transparent (the
// usual case for outline / fresnel-rim shaders), Godot ignores
// `render_priority` and depth-sorts the two passes back-to-front based
// on their bounding box / camera distance. Because the outline pass is
// usually authored slightly *behind* the mesh in object space (so its
// extruded silhouette doesn't clip the base mesh), the depth sort puts
// outline first and the base mesh second; the alpha-blended base mesh
// then composites *over* the outline at the centre, defeating the
// effect the user set out to achieve.
//
// At the GL layer the symptom is: two alpha-blended draw calls in an
// order that contradicts the user-set render_priority, observable as
// the wrong final pixel where the two materials overlap.
#include <GL/gl.h>
#include <GL/glx.h>
#include <X11/Xlib.h>
#include <stdio.h>

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
typedef void   (*PFNVAP)(GLuint, GLint, GLenum, GLboolean, GLsizei, const void*);
typedef void   (*PFNEVA)(GLuint);
typedef GLint  (*PFNGUL)(GLuint, const char*);
typedef void   (*PFNU4F)(GLint, GLfloat, GLfloat, GLfloat, GLfloat);
typedef GLXContext (*PFNCCAA)(Display*, GLXFBConfig, GLXContext, Bool, const int*);

#define GP(T,N) (T)glXGetProcAddressARB((const GLubyte*)N)

static const char* VS =
"#version 330 core\n"
"layout(location=0) in vec2 a_pos;\n"
"void main(){ gl_Position = vec4(a_pos, 0.0, 1.0); }\n";
static const char* FS =
"#version 330 core\n"
"uniform vec4 u_rgba;\n"
"out vec4 o;\n"
"void main(){ o = u_rgba; }\n";

#define W 256
#define H 256

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
    PFNCCAA create_ctx = GP(PFNCCAA,"glXCreateContextAttribsARB");
    int ca[] = {
        GLX_CONTEXT_MAJOR_VERSION_ARB, 3,
        GLX_CONTEXT_MINOR_VERSION_ARB, 3,
        GLX_CONTEXT_PROFILE_MASK_ARB, GLX_CONTEXT_CORE_PROFILE_BIT_ARB, 0
    };
    GLXContext ctx = create_ctx(dpy, fbc[0], 0, True, ca);
    glXMakeCurrent(dpy, win, ctx);

    PFNCS cs = GP(PFNCS,"glCreateShader");
    PFNSS ss = GP(PFNSS,"glShaderSource");
    PFNCMP cmp= GP(PFNCMP,"glCompileShader");
    PFNCP cp = GP(PFNCP,"glCreateProgram");
    PFNAS as = GP(PFNAS,"glAttachShader");
    PFNLP lp = GP(PFNLP,"glLinkProgram");
    PFNUP up = GP(PFNUP,"glUseProgram");
    PFNGEN gva = GP(PFNGEN,"glGenVertexArrays");
    PFNBIND bva= GP(PFNBIND,"glBindVertexArray");
    PFNGEN gb  = GP(PFNGEN,"glGenBuffers");
    PFNBINDB bb= GP(PFNBINDB,"glBindBuffer");
    PFNBD  bd  = GP(PFNBD,"glBufferData");
    PFNVAP vap = GP(PFNVAP,"glVertexAttribPointer");
    PFNEVA eva = GP(PFNEVA,"glEnableVertexAttribArray");
    PFNGUL gul = GP(PFNGUL,"glGetUniformLocation");
    PFNU4F u4f = GP(PFNU4F,"glUniform4f");

    GLuint vs = cs(GL_VERTEX_SHADER); ss(vs,1,&VS,NULL); cmp(vs);
    GLuint fs = cs(GL_FRAGMENT_SHADER); ss(fs,1,&FS,NULL); cmp(fs);
    GLuint prog = cp(); as(prog,vs); as(prog,fs); lp(prog);

    GLuint vao; gva(1,&vao); bva(vao);

    /* The outline mesh: a slightly larger quad authored "behind" the
       base mesh in object space (z = -0.5). User wants this to render
       LAST (priority=1) so the outline shows around / on top of the
       base. */
    float outline[] = { -0.6f,-0.6f,  0.6f,-0.6f, -0.6f, 0.6f,
                        -0.6f, 0.6f,  0.6f,-0.6f,  0.6f, 0.6f };
    /* The base mesh: smaller quad in front (in screen). User set
       render_priority=0 (default). */
    float base[]    = { -0.4f,-0.4f,  0.4f,-0.4f, -0.4f, 0.4f,
                        -0.4f, 0.4f,  0.4f,-0.4f,  0.4f, 0.4f };

    GLuint vbo_outline; gb(1,&vbo_outline); bb(GL_ARRAY_BUFFER, vbo_outline);
    bd(GL_ARRAY_BUFFER, sizeof(outline), outline, GL_STATIC_DRAW);
    GLuint vbo_base; gb(1,&vbo_base); bb(GL_ARRAY_BUFFER, vbo_base);
    bd(GL_ARRAY_BUFFER, sizeof(base), base, GL_STATIC_DRAW);

    glViewport(0,0,W,H);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    up(prog);
    GLint u_rgba = gul(prog,"u_rgba");

    /* Engine sort: transparent objects depth-sorted back→front; the
       outline (camera-relative further: object-space z = -0.5) goes
       FIRST despite render_priority = 1. This is the order
       glDrawArrays sees when render_priority is ignored. */

    /* Draw 1: outline (yellow, alpha=0.7). */
    bb(GL_ARRAY_BUFFER, vbo_outline);
    vap(0,2,GL_FLOAT,GL_FALSE,2*sizeof(float),(void*)0);
    eva(0);
    u4f(u_rgba, 1.0f, 0.95f, 0.0f, 0.7f);
    glDrawArrays(GL_TRIANGLES, 0, 6);

    /* Draw 2: base mesh (dark blue, alpha=0.7) — composited on top. */
    bb(GL_ARRAY_BUFFER, vbo_base);
    vap(0,2,GL_FLOAT,GL_FALSE,2*sizeof(float),(void*)0);
    eva(0);
    u4f(u_rgba, 0.05f, 0.10f, 0.45f, 0.7f);
    glDrawArrays(GL_TRIANGLES, 0, 6);

    glXSwapBuffers(dpy, win);
    glFinish();

    /* Centre is inside the base mesh. With the user's intent
       (outline last, render_priority=1) the centre should be yellow.
       With Godot's actual depth-sort behaviour the centre is dominated
       by the base mesh's blue. */
    unsigned char px[4] = {0};
    glReadPixels(W/2, H/2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
    fprintf(stderr,
            "centre = %u,%u,%u,%u (intended yellow ≈ 230,217,53; "
            "actual depth-sorted ≈ blue-dominant means render_priority "
            "ignored)\n",
            px[0], px[1], px[2], px[3]);

    glXMakeCurrent(dpy, None, NULL);
    glXDestroyContext(dpy, ctx);
    XDestroyWindow(dpy, win);
    XCloseDisplay(dpy);
    return 0;
}
