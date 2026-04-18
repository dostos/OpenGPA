# R9: BlendLayers uniform arrays exceed GL_MAX_FRAGMENT_UNIFORM_COMPONENTS

## Bug
A fragment shader declares three large uniform arrays (`float[]`, `int[]`,
`vec2[]`) whose combined component count exceeds
`GL_MAX_FRAGMENT_UNIFORM_COMPONENTS`. The program link silently fails and
subsequent draws produce nothing. The caller never inspects
`GL_LINK_STATUS` or the program info log, so the only symptom is a blank
frame.

## Expected Correct Output
A full-screen quad tinted from the uniform arrays covers the window.

## Actual Broken Output
The window stays the clear color (dark blue ≈ RGB 0,0,102) — the draw call
is a no-op because the shader program failed to link.

## Ground Truth Diagnosis
Pixelorama #938 describes this exactly. The BlendLayers shader (introduced
in PR #911) declares:

> ```glsl
> uniform float[1024] opacities;
> uniform int[1024] blend_modes;
> uniform vec2[1024] origins;
> ```

On the reporter's desktop (GTX 1060) the GPU limit accommodates these
arrays, so blending renders correctly. On a mobile GPU it does not:

> "on my Android device, Huawei P Smart (GPU: Mali-T830 MP2), this is not
> working ... lowering the length to 256 on all three uniforms is working."

OpenGL ES 3.0 only guarantees `MAX_FRAGMENT_UNIFORM_COMPONENTS >= 896`,
and many mobile drivers expose close to that minimum. Declaring
1024 × float + 1024 × int + 1024 × vec2 = 4096 components overflows the
limit; the fragment program link fails, `glUseProgram` silently has no
effect, and the draw emits nothing. Because the Godot-level code in
`ShaderImageEffect.gd` never checks `get_link_status()` equivalent or the
info log, the failure surfaces only as a blank canvas. The reproducer
scales each array to 8192 elements so the same link-time overflow
triggers on desktop GPUs whose typical limit is 4096 components.

## Difficulty Rating
3/5

## Adversarial Principles
- silent-link-failure
- gpu-capability-divergence
- no-error-check-after-shader-build

## How OpenGPA Helps
Querying the active shader program exposes `GL_LINK_STATUS == GL_FALSE`
and the info log ("fragment shader uses too many uniform components")
immediately. Without that, the agent sees only a blank framebuffer and
must guess which stage of the pipeline dropped the geometry.

## Source
- **URL**: https://github.com/Orama-Interactive/Pixelorama/issues/938
- **Type**: issue
- **Date**: 2023-09-05
- **Commit SHA**: (n/a)
- **Attribution**: Reported by @OverloadedOrama (see linked PR #911)

## Tier
core

## API
opengl

## Framework
none

## Bug Signature
```yaml
type: framebuffer_dominant_color
spec:
  dominant_color_rgba: [0, 0, 102, 255]
  min_fraction: 0.95
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: OpenGPA's shader-program inspection surfaces
  `GL_LINK_STATUS` and the program info log directly; the root cause
  (uniform component overflow) is in that log line. Without OpenGPA, the
  agent only sees an empty frame and has to probe many candidate causes
  (clear-color mismatch, missing viewport, wrong VAO binding, etc.)
  before reaching the shader linker.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
