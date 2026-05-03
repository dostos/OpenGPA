# R53_SUBVIEWPORT_FEEDBACK_LOOP_SCREEN_SHADER_GODOT: SubViewport screen-shader feedback loop (Godot)

## Bug
A `SubViewport` is given a `CanvasItem` material whose fragment shader
samples `SCREEN_TEXTURE` via `hint_screen_texture`. Godot's renderer binds
the SubViewport's color attachment as the destination of the screen-shader
draw *and* as the sampler the shader reads from. The same texture is
simultaneously `GL_COLOR_ATTACHMENT0` of the active FBO and the
`sampler2D` the fragment shader samples. The output is undefined per the
GL spec (feedback loop): on most consumer drivers the screen-shader pass
samples stale or partially-written content, producing the "duplicated
SubViewport" symptom in the bug report.

## Expected Correct Output
With a properly ping-ponged screen shader (the SubViewport content is
sampled out of one texture and written into a *different* destination
texture), the user's intended channel rotation `o = vec4(c.b, c.r,
c.g, 1.0)` against red (≈229, 25, 25) yields green (≈25, 229, 25) in
the SubViewport, and a passthrough blit to the default framebuffer
shows green at the centre pixel.

## Actual Broken Output
The screen-shader pass reads from its own draw target. Per the GL spec
the result is undefined — and observed behaviour is genuinely
driver-divergent: on macOS (the platform the issue was filed against),
Godot reports the SubViewport "draws once with the original texture
and then draws AGAIN with the shader effect on top", i.e. the
pre-shader red bleeds through the screen-shader output. On
Mesa/Intel/AMD-Linux the loop frequently appears to "work" — the
centre pixel is green and the visible output is what the user
intended, even though the FBO state still violates the spec. The bug
is a *latent* feedback loop that surfaces only on specific drivers
and frame phases, which is the dimension the user-visible report
emphasises ("works in editor, broken on macOS").

## Ground Truth Diagnosis
The user's code creates a textbook GL feedback loop: the texture object
that backs `GL_COLOR_ATTACHMENT0` of the currently-bound FBO is also
bound to `GL_TEXTURE0` and read by the fragment shader's `u_screen`
sampler. The OpenGL spec (4.6 §9.3.1) makes this case undefined unless
the fragment that writes pixel P samples the same texel only at level
zero with a coordinate that maps exactly to P (which is not true here:
the screen shader samples its own UV neighbourhood).

The Godot reporter described the same surface symptom:

> The SubViewPort will draw the original texture (pre-shader) and then
> draw AGAIN with the shader effect on top.

That "double-draw" appearance is exactly what happens when a driver
satisfies the feedback-loop draw with a mix of cached pre-write and
freshly-written texels. The fix on the Godot side is to ping-pong
through a second FBO so the screen shader's source texture is *not* the
current draw target; on the consumer side, restructuring the SubViewport
to render its content with a distinct `BackBufferCopy` material achieves
the same.

## Difficulty Rating
4/5

## Adversarial Principles
- feedback-loop-undefined-behaviour
- same-texture-as-color-attachment-and-sampler
- visual-symptom-resembles-double-render-not-feedback-loop
- driver-divergent (works on some, glitchy on others)

## How OpenGPA Helps
OpenGPA tracks FBO attachments and per-draw sampler bindings (see the
recent `feat: track FBO attachments — detect feedback loops` commit). A
single query for "which textures are bound as samplers for draw call N
and also as color/depth attachments of the active FBO at draw call N"
returns `subvp_tex`, immediately surfacing the feedback loop. The agent
then maps that GL-level fact back to the Godot pattern (`SCREEN_TEXTURE`
inside a SubViewport with no intermediate copy) without having to guess
from the visually-ambiguous "doubled" symptom.

## Source
- **URL**: https://github.com/godotengine/godot/issues/92058
- **Type**: issue
- **Date**: 2024-05-19
- **Commit SHA**: (n/a)
- **Attribution**: Reported on Godot 4.2.2.stable / 4.3-dev6 (macOS Sonoma); reproduction reduced to GL feedback-loop primitives for the eval

## Tier
core

## API
opengl

## Framework
none

## Bug Signature
```yaml
type: unexpected_state_in_draw
spec:
  description: |
    For the screen-shader draw call (the second glDrawArrays issued
    against the SubViewport FBO), the texture bound to the
    `u_screen` sampler must NOT also be bound as a colour attachment
    of the active framebuffer. A correct rendering of the same
    effect ping-pongs through a second FBO so the read and write
    targets are distinct.
  detection:
    same_texture_as_color_attachment_and_sampler: true
  rationale: |
    A pure-screenshot scorer cannot reliably detect this on
    permissive drivers (Mesa/Linux): the visible output is often
    the user-intended green, masking the latent feedback loop. The
    state-level check identifies the bug regardless of driver.
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The defect is a pure GL state anomaly — same texture object on both sides of a draw call's read/write set. OpenGPA's per-draw FBO-attachment + sampler-binding trace exposes the conflict directly; no inference about shader semantics or Godot internals is required to identify it. Crucially, this is one of the cases where a screenshot-only diagnostic agent will report "looks fine" on Linux/Mesa while a macOS user is reporting the bug — OpenGPA's state inspection bridges that gap.
