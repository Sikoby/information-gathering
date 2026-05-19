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


# Smoky/ethereal volumetric form: iterated domain-warping over 3D value noise,
# then a ridge function turns the smooth field into sharp filament-like
# contours. The result reads as multiple intertwined wisps of light, softly
# dispersing at the edges. Pure grayscale, mild warm tint at hottest peaks.
# Audio amplitude pumps brightness + scale; state nudges motion speed.
_FRAGMENT_SHADER = """
#version 330
out vec4 fragColor;

uniform vec3  iResolution;
uniform float iTime;
uniform float iAudioAmp;   // 0..1 smoothed RMS of agent's outbound speech
uniform int   iState;      // 0 listening, 1 thinking, 2 speaking

float hash(vec3 p) {
    p = fract(p * vec3(443.8975, 397.2973, 491.1871));
    p += dot(p, p.yzx + 19.19);
    return fract((p.x + p.y) * p.z);
}

float vnoise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash(i + vec3(0.0, 0.0, 0.0));
    float n100 = hash(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash(i + vec3(1.0, 1.0, 1.0));
    return mix(
        mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
        mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y),
        f.z
    );
}

float fbm(vec3 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
        v += a * vnoise(p);
        p *= 2.03;
        a *= 0.5;
    }
    return v;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);

    // State-dependent motion tempo.
    float speed = 0.18;
    if (iState == 1) speed = 0.30;          // thinking — flowier
    else if (iState == 2) speed = 0.22 + 0.20 * iAudioAmp;  // speaking — punchier with amp

    // Slow asymmetric drift so the form wanders off-center like the reference.
    vec2 drift = vec2(sin(iTime * 0.27) * 0.18, cos(iTime * 0.31) * 0.14);
    uv -= drift;

    // Iterated domain warping (Inigo Quilez warp technique).
    // Each warp pass folds the field into more complex, fluid filaments.
    vec3 p = vec3(uv * 1.6, iTime * speed);
    vec3 q = vec3(
        fbm(p + vec3(0.0, 0.0, 0.0)),
        fbm(p + vec3(5.2, 1.3, 0.0)),
        fbm(p + vec3(8.3, 2.8, 1.7))
    );
    vec3 r = vec3(
        fbm(p + 2.0 * q + vec3(1.7, 9.2, 0.0)),
        fbm(p + 2.0 * q + vec3(8.3, 2.8, 1.7)),
        fbm(p + 2.0 * q + vec3(4.1, 6.4, 3.3))
    );
    float n = fbm(p + 3.5 * r);

    // Ridge function — turns smooth field into sharp filament contours.
    float ridge = 1.0 - abs(2.0 * n - 1.0);
    ridge = pow(ridge, 5.0);

    // Soft radial envelope so the form has a body and fades to black at edges.
    float d = length(uv);
    float envelope = exp(-d * 1.4);

    // Audio-driven brightness pump.
    float amp = clamp(iAudioAmp, 0.0, 1.0);
    float pulse = 1.0 + 1.4 * amp;
    if (iState == 0) pulse *= 0.65;         // listening: subdued
    else if (iState == 1) pulse *= 0.85;    // thinking: medium

    // Compose: ridges carry the bright filaments, envelope adds soft body.
    float bright = (ridge * 1.5 + envelope * 0.18) * pulse;
    bright = clamp(bright, 0.0, 1.6);

    // Slight warm tint at hottest peaks (matches the reference's faint amber
    // glow around the brightest crests).
    vec3 col = vec3(bright);
    col += vec3(0.18, 0.10, 0.04) * max(bright - 0.85, 0.0);

    // Tone curve so highlights stay crisp and shadows roll off softly.
    col = pow(col, vec3(0.92));

    // Alpha follows brightness so the form composites cleanly on dark UIs.
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
