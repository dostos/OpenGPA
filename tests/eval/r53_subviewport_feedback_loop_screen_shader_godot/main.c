// SOURCE: https://github.com/godotengine/godot/issues/92058
//
// Godot consumer pattern: a SubViewport with a CanvasItem material that
// samples SCREEN_TEXTURE to apply a "screen shader". The Godot engine binds
// the SubViewport's color attachment as the destination of the active draw
// AND as the sampler the screen-shader reads from, producing duplicated /
// stale samples ("the SubViewport draws once with the original texture and
// then draws AGAIN with the shader effect on top"). At the GL level the
// pattern is: the same texture object is simultaneously COLOR_ATTACHMENT0
// of the bound FBO and TEXTURE_2D unit 0 in the screen-shader draw.
#include <GL/gl.h>
#include <GL/glx.h>
#include <X11/Xlib.h>
#include <stdio.h>
#include <stdlib.h>

#define GL_FRAMEBUFFER         0x8D40
#define GL_COLOR_ATTACHMENT0   0x8CE0
#define GL_FRAMEBUFFER_COMPLETE 0x8CD5

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
typedef GLint  (*PFNGUL)(GLuint, const char*);
typedef void   (*PFNU1I)(GLint, GLint);
typedef void   (*PFNAT)(GLenum);
typedef GLXContext (*PFNCCAA)(Display*, GLXFBConfig, GLXContext, Bool, const int*);

#define GP(T,N) (T)glXGetProcAddressARB((const GLubyte*)N)

static const char* QUAD_VS =
"#version 330 core\n"
"layout(location=0) in vec2 a_pos;\n"
"out vec2 v_uv;\n"
"void main(){ v_uv = a_pos*0.5+0.5; gl_Position = vec4(a_pos,0,1); }\n";

static const char* SOLID_FS =
"#version 330 core\n"
"in vec2 v_uv;\n"
"out vec4 o;\n"
"void main(){ o = vec4(0.9, 0.1, 0.1, 1.0); }\n";

// "Screen shader" of a Godot CanvasItem material with hint_screen_texture:
// reads the SubViewport's own color attachment and rotates RGB → BGR.
static const char* SCREEN_FS =
"#version 330 core\n"
"in vec2 v_uv;\n"
"uniform sampler2D u_screen;\n"
"out vec4 o;\n"
"void main(){\n"
"  vec3 c = texture(u_screen, v_uv).rgb;\n"
"  o = vec4(c.b, c.r, c.g, 1.0);\n"
"}\n";

// Passthrough used to copy subvp_tex to the default framebuffer for
// inspection.
static const char* PASSTHRU_FS =
"#version 330 core\n"
"in vec2 v_uv;\n"
"uniform sampler2D u_screen;\n"
"out vec4 o;\n"
"void main(){ o = texture(u_screen, v_uv); }\n";

static GLuint compile_program(PFNCS cs, PFNSS ss, PFNCMP cmp,
                              PFNCP cp, PFNAS as, PFNLP lp,
                              const char* vs_src, const char* fs_src) {
    GLuint vs = cs(GL_VERTEX_SHADER);
    ss(vs, 1, &vs_src, NULL); cmp(vs);
    GLuint fs = cs(GL_FRAGMENT_SHADER);
    ss(fs, 1, &fs_src, NULL); cmp(fs);
    GLuint p = cp();
    as(p, vs); as(p, fs); lp(p);
    return p;
}

#define W 256
#define H 256

int main(void){
    Display* dpy = XOpenDisplay(NULL);
    if (!dpy){ fprintf(stderr,"no display\n"); return 1; }
    int attrs[] = {
        GLX_X_RENDERABLE, True, GLX_DRAWABLE_TYPE, GLX_WINDOW_BIT,
        GLX_RENDER_TYPE, GLX_RGBA_BIT,
        GLX_RED_SIZE, 8, GLX_GREEN_SIZE, 8, GLX_BLUE_SIZE, 8, GLX_ALPHA_SIZE, 8,
        GLX_DEPTH_SIZE, 24, GLX_DOUBLEBUFFER, True, None
    };
    int n=0;
    GLXFBConfig* fbc = glXChooseFBConfig(dpy, DefaultScreen(dpy), attrs, &n);
    if (!fbc || !n){ fprintf(stderr,"no fbc\n"); return 1; }
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

    PFNCS  cs  = GP(PFNCS,  "glCreateShader");
    PFNSS  ss  = GP(PFNSS,  "glShaderSource");
    PFNCMP cmp = GP(PFNCMP, "glCompileShader");
    PFNCP  cp  = GP(PFNCP,  "glCreateProgram");
    PFNAS  as  = GP(PFNAS,  "glAttachShader");
    PFNLP  lp  = GP(PFNLP,  "glLinkProgram");
    PFNUP  up  = GP(PFNUP,  "glUseProgram");
    PFNGEN gva = GP(PFNGEN, "glGenVertexArrays");
    PFNBIND bva= GP(PFNBIND,"glBindVertexArray");
    PFNGEN gb  = GP(PFNGEN, "glGenBuffers");
    PFNBINDB bb= GP(PFNBINDB,"glBindBuffer");
    PFNBD  bd  = GP(PFNBD,  "glBufferData");
    PFNVAP vap = GP(PFNVAP, "glVertexAttribPointer");
    PFNEVA eva = GP(PFNEVA, "glEnableVertexAttribArray");
    PFNGENFB gfb = GP(PFNGENFB,"glGenFramebuffers");
    PFNBINDFB bfb= GP(PFNBINDFB,"glBindFramebuffer");
    PFNFBT2D fbt = GP(PFNFBT2D,"glFramebufferTexture2D");
    PFNCFB  cfb  = GP(PFNCFB,  "glCheckFramebufferStatus");
    PFNGUL  gul  = GP(PFNGUL,  "glGetUniformLocation");
    PFNU1I  u1i  = GP(PFNU1I,  "glUniform1i");
    PFNAT   atu  = GP(PFNAT,   "glActiveTexture");

    /* The "SubViewport" color texture: */
    GLuint subvp_tex;
    glGenTextures(1, &subvp_tex);
    glBindTexture(GL_TEXTURE_2D, subvp_tex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

    /* The "SubViewport" FBO. */
    GLuint subvp_fbo;
    gfb(1, &subvp_fbo);
    bfb(GL_FRAMEBUFFER, subvp_fbo);
    fbt(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, subvp_tex, 0);
    if (cfb(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE){
        fprintf(stderr,"FBO incomplete\n"); return 1;
    }

    GLuint vao; gva(1,&vao); bva(vao);
    float quad[] = { -1,-1,  1,-1,  -1,1,   -1,1, 1,-1, 1,1 };
    GLuint vbo; gb(1,&vbo); bb(GL_ARRAY_BUFFER, vbo);
    bd(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    vap(0,2,GL_FLOAT,GL_FALSE,2*sizeof(float),(void*)0);
    eva(0);

    GLuint p_solid    = compile_program(cs,ss,cmp,cp,as,lp, QUAD_VS, SOLID_FS);
    GLuint p_screen   = compile_program(cs,ss,cmp,cp,as,lp, QUAD_VS, SCREEN_FS);
    GLuint p_passthru = compile_program(cs,ss,cmp,cp,as,lp, QUAD_VS, PASSTHRU_FS);

    /* Pass 1: paint the SubViewport red. */
    bfb(GL_FRAMEBUFFER, subvp_fbo);
    glViewport(0,0,W,H);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);
    up(p_solid);
    glDrawArrays(GL_TRIANGLES, 0, 6);

    /* Pass 2 — the Godot "screen shader" pass. The SubViewport's own
       color attachment is sampled while it is still bound as the draw
       destination — the feedback-loop pattern from #92058. */
    /* (FBO subvp_fbo still bound, subvp_tex is COLOR_ATTACHMENT0.) */
    atu(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, subvp_tex);
    up(p_screen);
    u1i(gul(p_screen, "u_screen"), 0);
    glDrawArrays(GL_TRIANGLES, 0, 6);

    /* Pass 3: copy the subvp_tex to the default framebuffer (passthrough)
       so the user / eval can see what pass 2 left in the SubViewport. */
    bfb(GL_FRAMEBUFFER, 0);
    glViewport(0,0,W,H);
    glClearColor(0,0,0,1);
    glClear(GL_COLOR_BUFFER_BIT);
    atu(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, subvp_tex);
    up(p_passthru);
    u1i(gul(p_passthru, "u_screen"), 0);
    glDrawArrays(GL_TRIANGLES, 0, 6);

    glFinish();
    unsigned char px[4] = {0};
    glReadPixels(W/2, H/2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, px);
    fprintf(stderr, "center pixel = %u,%u,%u,%u "
            "(intended green ≈ 25,229,25; on permissive drivers pass 2 may "
            "succeed and the centre is green; on strict drivers the feedback "
            "loop yields stale red or partially-written content)\n",
            px[0], px[1], px[2], px[3]);

    glXMakeCurrent(dpy, None, NULL);
    glXDestroyContext(dpy, ctx);
    XDestroyWindow(dpy, win);
    XCloseDisplay(dpy);
    return 0;
}
