"""Shader-based avatar renderer (Shadertoy-style GLSL via moderngl).

A single fragment shader runs per pixel each frame, driven by uniforms that
mirror Shadertoy conventions (`iTime`, `iResolution`) plus our own state:
`iAudioAmp`, `iState` (0 listening / 1 thinking / 2 speaking).

The shader is intentionally written in the Shadertoy idiom — swap in any
shader from shadertoy.com by replacing `_FRAGMENT_SHADER`, wiring its
uniforms, and adjusting `mainImage(...)` → `main()` if needed.

Public API matches the previous CPU renderer:
    render_frame(AnimationState, t) -> PIL.Image
so `avatar.py` doesn't need to know we switched backends.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Literal

import moderngl
import numpy as np
from PIL import Image

SemanticState = Literal["initializing", "idle", "listening", "thinking", "speaking"]


@dataclass
class AnimationState:
    semantic_state: SemanticState = "listening"
    amplitude: float = 0.0


CANVAS = 256

_STATE_CODE = {
    "initializing": 0,
    "idle": 0,
    "listening": 0,
    "thinking": 1,
    "speaking": 2,
}


_VERTEX_SHADER = """
#version 330
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""


# Centered stack of overlapping wispy ring loops: each ring is a soft
# glowing ellipse with a noise-wobbled radius and bright/dim arcs around
# its circumference. Six rings layered together at different radii,
# rotations, and aspects produce the intertwined-loops look of the
# reference image. Audio amplitude pumps brightness; semantic state
# tweaks rotation speed.
_FRAGMENT_SHADER = """
#version 330
out vec4 fragColor;

uniform vec3  iResolution;
uniform float iTime;
uniform float iAudioAmp;   // 0..1 smoothed RMS of agent's outbound speech
uniform int   iState;      // 0 listening, 1 thinking, 2 speaking

float hash2(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise2(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash2(i);
    float b = hash2(i + vec2(1.0, 0.0));
    float c = hash2(i + vec2(0.0, 1.0));
    float d = hash2(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm2(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 4; i++) {
        v += a * noise2(p);
        p *= 2.05;
        a *= 0.5;
    }
    return v;
}

// One wispy ring: rotated, stretched, noise-wobbled radius, with
// non-uniform brightness around the circumference (creates the look of
// distinct bright arcs along each ring rather than a uniform halo).
float ringWisp(vec2 p, float baseR, float angle, vec2 stretch, float thickness,
               float phase, float speed)
{
    float c = cos(angle);
    float s = sin(angle);
    p = mat2(c, -s, s, c) * p;
    p *= stretch;

    float r = length(p);
    float a = atan(p.y, p.x);

    // Smoky/non-circular boundary — radius wobbles with angular FBM.
    float wobble = 0.07 * (fbm2(vec2(a * 1.6 + iTime * speed + phase,
                                     iTime * 0.18 + phase)) - 0.5);
    float d = abs(r - (baseR + wobble));

    // Soft volumetric falloff (exp gives the smoky edge).
    float core = exp(-d * 22.0 / thickness);

    // Brightness along the ring is uneven — a few bright lobes per loop.
    float lobes = 0.45 + 0.55 * cos(a * 2.3 + iTime * speed * 1.4 + phase);
    return core * (0.4 + 0.9 * lobes);
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);

    float amp = clamp(iAudioAmp, 0.0, 1.0);

    // State-dependent rotation tempo for the whole stack.
    float spin = 0.10;
    if (iState == 1) spin = 0.18;                 // thinking — restless
    else if (iState == 2) spin = 0.12 + 0.18 * amp; // speaking — drives with amp

    // Subtle audio-driven scale breathing.
    float pulse = 1.0 + 0.10 * amp;

    // Six overlapping rings: different base radii, rotation offsets,
    // aspect ratios, and phases give the layered look.
    float total = 0.0;
    total += ringWisp(uv, 0.30 * pulse, iTime * spin * 1.0,        vec2(1.00, 1.00), 1.0, 0.0,  spin);
    total += ringWisp(uv, 0.34 * pulse, iTime * spin * 0.85 + 1.0, vec2(1.18, 0.85), 1.0, 2.1,  spin);
    total += ringWisp(uv, 0.24 * pulse, -iTime * spin * 1.1 + 2.0, vec2(0.88, 1.12), 0.9, 4.3,  spin);
    total += ringWisp(uv, 0.40 * pulse, iTime * spin * 0.70 + 3.0, vec2(1.07, 0.94), 1.2, 6.5,  spin);
    total += ringWisp(uv, 0.18 * pulse, -iTime * spin * 1.3,       vec2(1.00, 1.00), 0.85, 8.7, spin);
    total += ringWisp(uv, 0.46 * pulse, iTime * spin * 0.55 + 5.0, vec2(0.95, 1.05), 1.3, 10.9, spin);

    // Audio brightness pump.
    float bright = total * (0.85 + 1.4 * amp);
    if (iState == 0) bright *= 0.75;   // listening: subdued

    bright = clamp(bright, 0.0, 1.8);

    // Slight warm tint at the brightest ring intersections.
    vec3 col = vec3(bright);
    col += vec3(0.16, 0.10, 0.04) * max(bright - 0.95, 0.0);

    // Gamma for crisp filaments and soft shadows.
    col = pow(max(col, 0.0), vec3(0.92));

    // Alpha mirrors brightness so the form composites cleanly on dark UIs.
    float alpha = clamp(bright * 1.1, 0.0, 1.0);

    fragColor = vec4(col, alpha);
}
"""


class _ShaderRenderer:
    """Owns the moderngl context, framebuffer, and shader program."""

    def __init__(self, size: int = CANVAS) -> None:
        self._size = size
        self._ctx = moderngl.create_standalone_context(backend="egl")
        self._prog = self._ctx.program(
            vertex_shader=_VERTEX_SHADER,
            fragment_shader=_FRAGMENT_SHADER,
        )
        # Full-screen triangle (covers the viewport in one primitive).
        verts = np.array([-1.0, -1.0, 3.0, -1.0, -1.0, 3.0], dtype="f4")
        self._vbo = self._ctx.buffer(verts.tobytes())
        self._vao = self._ctx.vertex_array(self._prog, [(self._vbo, "2f", "in_pos")])
        self._tex = self._ctx.texture((size, size), 4)
        self._fbo = self._ctx.framebuffer(color_attachments=[self._tex])

        self._prog["iResolution"].value = (float(size), float(size), 1.0)

    def render(self, state: AnimationState, t: float) -> Image.Image:
        self._prog["iTime"].value = float(t)
        self._prog["iAudioAmp"].value = float(state.amplitude)
        self._prog["iState"].value = _STATE_CODE.get(state.semantic_state, 0)

        self._fbo.use()
        self._ctx.clear(0.0, 0.0, 0.0, 0.0)
        self._vao.render(moderngl.TRIANGLES, vertices=3)
        raw = self._fbo.read(components=4)
        # OpenGL origin is bottom-left; flip to image conventions.
        return Image.frombytes("RGBA", (self._size, self._size), raw).transpose(
            Image.FLIP_TOP_BOTTOM
        )


_renderer: _ShaderRenderer | None = None
_lock = threading.Lock()


def render_frame(state: AnimationState, t: float) -> Image.Image:
    global _renderer
    if _renderer is None:
        with _lock:
            if _renderer is None:
                _renderer = _ShaderRenderer()
    return _renderer.render(state, t)
