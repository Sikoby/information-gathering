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


# An iridescent "consultant orb": volumetric glow, noise-displaced rim,
# Apple-Intelligence-style cyan→magenta→violet gradient. Pulses with
# `iAudioAmp`, de-saturates while thinking, brightens while speaking.
_FRAGMENT_SHADER = """
#version 330
out vec4 fragColor;

uniform vec3  iResolution;
uniform float iTime;
uniform float iAudioAmp;   // 0..1 smoothed RMS of agent's outbound speech
uniform int   iState;      // 0 listening, 1 thinking, 2 speaking

#define PI 3.14159265

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
        v += a * noise(p);
        p *= 2.02;
        a *= 0.5;
    }
    return v;
}

// Iridescent palette (Inigo Quilez cosine palette tuned for cyan/magenta/violet).
vec3 palette(float t) {
    vec3 a = vec3(0.55, 0.45, 0.65);
    vec3 b = vec3(0.45, 0.35, 0.45);
    vec3 c = vec3(1.00, 1.00, 1.00);
    vec3 d = vec3(0.10, 0.30, 0.65);
    return a + b * cos(2.0 * PI * (c * t + d));
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);
    float r = length(uv);
    float ang = atan(uv.y, uv.x);

    // Base radius, modulated by audio. Thinking has a gentle pulse instead.
    float baseR = 0.30;
    float amp = clamp(iAudioAmp, 0.0, 1.0);
    if (iState == 2) baseR += 0.10 * amp;
    if (iState == 1) baseR += 0.012 * sin(iTime * 1.5);
    if (iState == 0) baseR += 0.008 * sin(iTime * 0.9);

    // Noise-displaced rim (turbulent perimeter).
    float n = fbm(vec2(ang * 2.5 + iTime * 0.35, iTime * 0.18));
    float rim = baseR + 0.045 * (n - 0.5) + 0.06 * amp * (n - 0.5);

    // Soft signed distance to the orb boundary; interior + falloff glow.
    float d = r - rim;
    float disc = smoothstep(0.02, -0.04, d);
    float glow = exp(-max(d, 0.0) * 9.0);

    // Coloring: angular + temporal sweep across the iridescent palette.
    float t = ang / (2.0 * PI) + iTime * 0.08 + 0.6 * n;
    vec3 col = palette(t);

    // State tweaks.
    if (iState == 1) {
        // Thinking: pull color toward a cool slate.
        col = mix(vec3(0.45, 0.50, 0.65), col, 0.35);
    } else if (iState == 2) {
        // Speaking: brighten and slightly warm.
        col *= 1.10 + 0.20 * amp;
    } else {
        // Listening/idle: gentle dim.
        col *= 0.85;
    }

    // Composite: bright interior + soft external bloom.
    vec3 final = col * (disc * 0.85 + glow * 0.55);
    float alpha = clamp(disc + glow * 0.5, 0.0, 1.0);

    // Inner highlight (off-axis) for depth.
    vec2 hilightOff = vec2(-0.10, 0.12);
    float hr = length(uv - hilightOff);
    float hilite = exp(-hr * 14.0) * 0.35;
    final += vec3(1.0) * hilite * disc;

    // Subtle film-grain to avoid banding.
    float grain = (hash(gl_FragCoord.xy + iTime) - 0.5) * 0.015;
    final += grain;

    // Tone-mapping-ish: gentle gamma + clamp.
    final = pow(max(final, 0.0), vec3(0.90));
    fragColor = vec4(final, alpha);
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
