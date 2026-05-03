// SOURCE: https://github.com/godotengine/godot/issues/80991
//
// Godot Forward Mobile + MSAA: a ShaderMaterial samples DEPTH_TEXTURE
// (hint_depth_texture). The Forward Mobile path renders the scene to a
// multisample depth attachment but forgets to resolve it into the
// non-MSAA depth texture before binding it for sampling — the user
// reports "the Depth Textures sampled data to be corrupted. Most likely
// its missing an MSAA Resolve before being bound." On consumer hardware
// the bound non-MSAA depth texture still holds its initial cleared
// value (1.0), so any consumer outline / fog / SSAO shader that depends
// on `DEPTH_TEXTURE < 1.0` produces no visible effect.
//
// This reproduction faithfully mirrors the lifecycle:
//   1. Render a centred quad to an MSAA FBO with depth-write on.
//   2. Resolve only the COLOR attachment to a non-MSAA FBO via
//      glBlitFramebuffer (forgetting the GL_DEPTH_BUFFER_BIT).
//   3. A "post-process" outline pass samples the non-MSAA depth
//      texture, writing magenta where depth < 0.99 and black otherwise.
//   4. Because the non-MSAA depth was never resolved into, every texel
//      reads 1.0 → the outline pass writes black everywhere → bug.
#include <GL/gl.h>
#include <GL/glx.h>
#include <X11/Xlib.h>
#include <stdio.h>

#define GL_FRAMEBUFFER          0x8D40
#define GL_READ_FRAMEBUFFER     0x8CA8
#define GL_DRAW_FRAMEBUFFER     0x8CA9
#define GL_COLOR_ATTACHMENT0    0x8CE0
#define GL_DEPTH_ATTACHMENT     0x8D00
#define GL_FRAMEBUFFER_COMPLETE 0x8CD5
#define GL_RENDERBUFFER         0x8D41
#define GL_DEPTH_COMPONENT24    0x81A6
#define GL_DEPTH_COMPONENT      0x1902
#define GL_TEXTURE_COMPARE_MODE 0x884C
#define GL_NONE                 0
#ifndef GL_TEXTURE_2D_MULTISAMPLE
#define GL_TEXTURE_2D_MULTISAMPLE 0x9100
#endif

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
typedef void   (*PFNGENFB)(GLsizei, GLuint*);
typedef void   (*PFNBINDFB)(GLenum, GLuint);
typedef void   (*PFNFBT2D)(GLenum, GLenum, GLenum, GLuint, GLint);
typedef GLenum (*PFNCFB)(GLenum);
typedef void   (*PFNGRB)(GLsizei, GLuint*);
typedef void   (*PFNBRB)(GLenum, GLuint);
typedef void   (*PFNRBSM)(GLenum, GLsizei, GLenum, GLsizei, GLsizei);
typedef void   (*PFNFBRB)(GLenum, GLenum, GLenum, GLuint);
typedef void   (*PFNBLIT)(GLint,GLint,GLint,GLint,GLint,GLint,GLint,GLint,GLbitfield,GLenum);
typedef GLint  (*PFNGUL)(GLuint, const char*);
typedef void   (*PFNU1I)(GLint, GLint);
typedef void   (*PFNU2F)(GLint, GLfloat, GLfloat);
typedef void   (*PFNAT)(GLenum);
typedef GLXContext (*PFNCCAA)(Display*, GLXFBConfig, GLXContext, Bool, const int*);

#define GP(T,N) (T)glXGetProcAddressARB((const GLubyte*)N)

static const char* SCENE_VS =
"#version 330 core\n"
"layout(location=0) in vec3 a_pos;\n"
"void main(){ gl_Position = vec4(a_pos, 1.0); }\n";
static const char* SCENE_FS =
"#version 330 core\n"
"out vec4 o;\n"
"void main(){ o = vec4(0.7, 0.7, 0.7, 1.0); }\n";

static const char* PP_VS =
"#version 330 core\n"
"layout(location=0) in vec2 a_pos;\n"
"out vec2 v_uv;\n"
"void main(){ v_uv = a_pos*0.5+0.5; gl_Position = vec4(a_pos,0,1); }\n";
// Outline / fog post-pass: writes magenta wherever depth < 0.99,
// black elsewhere. This is the consumer's intent.
static const char* PP_FS =
"#version 330 core\n"
"in vec2 v_uv;\n"
"uniform sampler2D u_depth;\n"
"out vec4 o;\n"
"void main(){\n"
"  float d = texture(u_depth, v_uv).r;\n"
"  o = (d < 0.99) ? vec4(1.0, 0.0, 1.0, 1.0) : vec4(0.0,0.0,0.0,1.0);\n"
"}\n";

#define W 256
#define H 256
#define SAMPLES 4

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

    PFNCS  cs = GP(PFNCS,"glCreateShader");
    PFNSS  ss = GP(PFNSS,"glShaderSource");
    PFNCMP cmp= GP(PFNCMP,"glCompileShader");
    PFNCP  cp = GP(PFNCP,"glCreateProgram");
    PFNAS  as = GP(PFNAS,"glAttachShader");
    PFNLP  lp = GP(PFNLP,"glLinkProgram");
    PFNUP  up = GP(PFNUP,"glUseProgram");
    PFNGEN gva= GP(PFNGEN,"glGenVertexArrays");
    PFNBIND bva=GP(PFNBIND,"glBindVertexArray");
    PFNGEN gb = GP(PFNGEN,"glGenBuffers");
    PFNBINDB bb=GP(PFNBINDB,"glBindBuffer");
    PFNBD  bd = GP(PFNBD,"glBufferData");
    PFNVAP vap= GP(PFNVAP,"glVertexAttribPointer");
    PFNEVA eva= GP(PFNEVA,"glEnableVertexAttribArray");
    PFNGENFB gfb= GP(PFNGENFB,"glGenFramebuffers");
    PFNBINDFB bfb=GP(PFNBINDFB,"glBindFramebuffer");
    PFNFBT2D fbt2d=GP(PFNFBT2D,"glFramebufferTexture2D");
    PFNCFB cfb = GP(PFNCFB,"glCheckFramebufferStatus");
    PFNGRB grb = GP(PFNGRB,"glGenRenderbuffers");
    PFNBRB brb = GP(PFNBRB,"glBindRenderbuffer");
    PFNRBSM rbsm = GP(PFNRBSM,"glRenderbufferStorageMultisample");
    PFNFBRB fbrb = GP(PFNFBRB,"glFramebufferRenderbuffer");
    PFNBLIT blit = GP(PFNBLIT,"glBlitFramebuffer");
    PFNGUL gul = GP(PFNGUL,"glGetUniformLocation");
    PFNU1I u1i = GP(PFNU1I,"glUniform1i");
    PFNAT  atu = GP(PFNAT,"glActiveTexture");

    /* ---------- MSAA scene FBO ---------- */
    GLuint msaa_color_rb;
    grb(1,&msaa_color_rb); brb(GL_RENDERBUFFER, msaa_color_rb);
    rbsm(GL_RENDERBUFFER, SAMPLES, GL_RGBA8, W, H);
    GLuint msaa_depth_rb;
    grb(1,&msaa_depth_rb); brb(GL_RENDERBUFFER, msaa_depth_rb);
    rbsm(GL_RENDERBUFFER, SAMPLES, GL_DEPTH_COMPONENT24, W, H);
    GLuint fbo_msaa; gfb(1,&fbo_msaa); bfb(GL_FRAMEBUFFER, fbo_msaa);
    fbrb(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, msaa_color_rb);
    fbrb(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,  GL_RENDERBUFFER, msaa_depth_rb);
    if (cfb(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE){
        fprintf(stderr,"msaa fbo incomplete\n"); return 1;
    }

    /* ---------- Resolve FBO (non-MSAA) ---------- */
    GLuint resolve_color;
    glGenTextures(1,&resolve_color);
    glBindTexture(GL_TEXTURE_2D, resolve_color);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);

    GLuint resolve_depth;
    glGenTextures(1,&resolve_depth);
    glBindTexture(GL_TEXTURE_2D, resolve_depth);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT24, W, H, 0,
                 GL_DEPTH_COMPONENT, GL_FLOAT, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE);

    GLuint fbo_resolve; gfb(1,&fbo_resolve); bfb(GL_FRAMEBUFFER, fbo_resolve);
    fbt2d(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, resolve_color, 0);
    fbt2d(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,  GL_TEXTURE_2D, resolve_depth, 0);
    if (cfb(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE){
        fprintf(stderr,"resolve fbo incomplete\n"); return 1;
    }
    /* Initialise resolve_depth to the GL-default 1.0 (matches what an
       engine renderer does when first allocating a depth target). */
    glClearDepth(1.0);
    glClear(GL_DEPTH_BUFFER_BIT);

    /* ---------- Geometry / programs ---------- */
    GLuint vao; gva(1,&vao); bva(vao);
    /* A small centred triangle at z=-0.5 (so depth ≈ 0.25 after the
       default ortho-ish clip projection). */
    float tri[] = {
        -0.4f,-0.4f,-0.5f,
         0.4f,-0.4f,-0.5f,
         0.0f, 0.4f,-0.5f
    };
    GLuint vbo; gb(1,&vbo); bb(GL_ARRAY_BUFFER, vbo);
    bd(GL_ARRAY_BUFFER, sizeof(tri), tri, GL_STATIC_DRAW);
    vap(0,3,GL_FLOAT,GL_FALSE,3*sizeof(float),(void*)0);
    eva(0);
    GLuint scene_vs = cs(GL_VERTEX_SHADER); ss(scene_vs,1,&SCENE_VS,NULL); cmp(scene_vs);
    GLuint scene_fs = cs(GL_FRAGMENT_SHADER); ss(scene_fs,1,&SCENE_FS,NULL); cmp(scene_fs);
    GLuint p_scene = cp(); as(p_scene,scene_vs); as(p_scene,scene_fs); lp(p_scene);

    GLuint vbo_quad; gb(1,&vbo_quad); bb(GL_ARRAY_BUFFER, vbo_quad);
    float quad[] = { -1,-1, 1,-1, -1,1,  -1,1, 1,-1, 1,1 };
    bd(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    vap(0,2,GL_FLOAT,GL_FALSE,2*sizeof(float),(void*)0);
    eva(0);
    GLuint pp_vs = cs(GL_VERTEX_SHADER); ss(pp_vs,1,&PP_VS,NULL); cmp(pp_vs);
    GLuint pp_fs = cs(GL_FRAGMENT_SHADER); ss(pp_fs,1,&PP_FS,NULL); cmp(pp_fs);
    GLuint p_pp = cp(); as(p_pp,pp_vs); as(p_pp,pp_fs); lp(p_pp);

    /* ---------- Pass 1: render scene to MSAA FBO ---------- */
    bfb(GL_FRAMEBUFFER, fbo_msaa);
    glViewport(0,0,W,H);
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClearDepth(1.0);
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LESS);
    glDepthMask(GL_TRUE);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    bb(GL_ARRAY_BUFFER, vbo);
    vap(0,3,GL_FLOAT,GL_FALSE,3*sizeof(float),(void*)0);
    up(p_scene);
    glDrawArrays(GL_TRIANGLES, 0, 3);

    /* ---------- Pass 2: resolve COLOR ONLY (the bug). ----------
       Forward Mobile / consumer path forgot GL_DEPTH_BUFFER_BIT. */
    bfb(GL_READ_FRAMEBUFFER, fbo_msaa);
    bfb(GL_DRAW_FRAMEBUFFER, fbo_resolve);
    blit(0,0,W,H, 0,0,W,H, GL_COLOR_BUFFER_BIT, GL_NEAREST);

    /* ---------- Pass 3: post-process samples the (still-cleared) ----------
       resolve_depth as DEPTH_TEXTURE, expecting it to hold the scene's
       depth values. */
    bfb(GL_FRAMEBUFFER, 0);
    glDisable(GL_DEPTH_TEST);
    glViewport(0,0,W,H);
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    bb(GL_ARRAY_BUFFER, vbo_quad);
    vap(0,2,GL_FLOAT,GL_FALSE,2*sizeof(float),(void*)0);
    up(p_pp);
    atu(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, resolve_depth);
    u1i(gul(p_pp,"u_depth"), 0);
    glDrawArrays(GL_TRIANGLES, 0, 6);

    glFinish();
    /* Centre pixel maps to the centre of the scene triangle — depth ≈
       0.25 in the MSAA buffer, but resolve_depth still holds 1.0
       because the depth blit was skipped. So the post-process colour
       at the centre is black instead of magenta. */
    unsigned char px[4] = {0};
    glReadPixels(W/2, H/2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
    fprintf(stderr,
            "centre = %u,%u,%u,%u (expected magenta 255,0,255; "
            "black 0,0,0 means depth was never resolved)\n",
            px[0], px[1], px[2], px[3]);

    glXMakeCurrent(dpy, None, NULL);
    glXDestroyContext(dpy, ctx);
    XDestroyWindow(dpy, win);
    XCloseDisplay(dpy);
    return 0;
}
