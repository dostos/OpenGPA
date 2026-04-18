# R10_FEEDBACK_LOOP_TRANSMISSION_DOUBLESIDE: Texture sampled while still attached as COLOR_ATTACHMENT0

## Bug
A single `GL_TEXTURE_2D` object is the bound framebuffer's
`COLOR_ATTACHMENT0` and is simultaneously bound to texture unit 0 with the
active fragment program sampling from it. The draw call therefore reads
from the same texture object it is writing to — a framebuffer/texture
feedback loop.

## Expected Correct Output
The fullscreen quad blends a known input color sampled from
`transmissionSamplerMap` with a base tint, producing a deterministic
greenish-blue frame written into `transmissionTex`.

## Actual Broken Output
The draw call is dropped (or produces undefined results). The
`COLOR_ATTACHMENT0` retains the prior clear contents (yellow). On
WebGL/ANGLE the driver emits
`GL_INVALID_OPERATION: Feedback loop formed between Framebuffer and active Texture`
on every draw.

## Ground Truth Diagnosis
The transmission render target was constructed with `samples = 0` because
`antialias:false` causes `capabilities.samples` (which is sourced from
`gl.getParameter(gl.SAMPLES)` on the default framebuffer) to be `0`. With
`samples = 0` no MSAA renderbuffer is allocated, so the texture itself is
attached directly as `COLOR_ATTACHMENT0`. The back-face DoubleSide block
in `renderTransmissionPass()` then samples from
`transmissionRenderTarget.texture` while that very texture is the bound
framebuffer's color attachment.

The original three.js fix (PR #26177) explicitly relied on multisampling
to side-step this:

> #25502 introduced a feedback loop during the back-side transmission
> pass since the active render target is equal to the texture which is
> assigned to `transmissionSamplerMap`. […] This issue does not pop-up
> when `antialias` is set to `true` […] because setting `antialias` to
> `true` means the transmissive render target is multisampled.
> Multisampled render targets do have more than one framebuffer so using
> it as the active render target and as a texture does not produce a
> feedback loop.

PR #32444 then changed the hardcoded `samples: 4` to
`samples: capabilities.samples`, so the multisampling guarantee was lost
whenever the canvas had `antialias:false`, re-introducing the feedback
loop documented in #26177.

## Difficulty Rating
4/5

## Adversarial Principles
- bind-point collision (FBO color attachment vs. sampler unit)
- silent rendering failure (draw is dropped, prior contents persist)
- multi-PR regression (a fix's invariant is broken by a later refactor)
- platform-conditional reproduction (extension presence hides the bug)

## How OpenGPA Helps
A single query — "for the current draw call, list every bound texture
object and every framebuffer attachment object" — reveals that
`transmissionTex` appears in both lists. Inspecting `glGetError` after the
draw further confirms the feedback loop. Without OpenGPA the developer
sees only "the back faces don't render" and a wall of WebGL warnings.

## Source
- **URL**: https://github.com/mrdoob/three.js/issues/33060
- **Type**: issue
- **Date**: 2025-10-24
- **Commit SHA**: (n/a)
- **Attribution**: Reported on three.js issue tracker; root cause cross-referenced with PR #32444 (regression) and PR #26177 (original fix)

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
  rule: "no texture object bound to a sampler unit referenced by the active program may also be a color/depth/stencil attachment of the currently bound DRAW_FRAMEBUFFER"
  draw_call_index: 0
  offending_object_kind: texture
  appears_as:
    - sampler_binding: { unit: 0, uniform: "transmissionSamplerMap" }
    - framebuffer_attachment: { target: GL_DRAW_FRAMEBUFFER, attachment: GL_COLOR_ATTACHMENT0 }
  expected_gl_error: GL_INVALID_OPERATION
```

## Upstream Snapshot
- **Repo**: https://github.com/mrdoob/three.js
- **SHA**: c2c5685879290d304c226a493061f6461021864c
- **Relevant Files**:
  - src/renderers/WebGLRenderer.js
  - src/renderers/webgl/WebGLCapabilities.js
  - src/renderers/WebGLRenderTarget.js
  - src/renderers/webgl/WebGLTextures.js

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The bug is purely a binding-state collision visible at draw-call time. OpenGPA's per-draw inventory of texture-unit bindings and framebuffer attachments makes the feedback loop directly observable; no heuristic is required to identify the offending object — it is literally the same GL name on both sides.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
