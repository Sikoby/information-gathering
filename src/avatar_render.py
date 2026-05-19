"""Shader-based avatar renderer (Shadertoy-style GLSL via moderngl).

Adapted from a Shadertoy particle-with-smoke-trails shader. The original
shader is multi-pass with feedback buffers and an audio-FFT texture; we
collapse it to a single fragment pass plus a ping-pong texture for the
trail, with particle state simulated in Python and audio FFT computed
from the agent's TTS samples.

Public API (called by `avatar.py`):
    render_frame(AnimationState, t) -> PIL.Image
    push_audio_samples(np.int16 array)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
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

# Particle simulation constants — scaled from the original Shadertoy values
# (which assumed 60 fps) up to our 24 fps target so visual motion matches.
_FPS_SCALE = 60.0 / 24.0
_PARTICLE_COUNT = 3
_MAX_VELOCITY = 0.004 * _FPS_SCALE
_MAX_VELOCITY_CHANGE = 0.0003 * _FPS_SCALE
_FOCAL_POINT_TENDENCY = 0.0002 * _FPS_SCALE
_TRAIL_DECAY = 0.995 ** _FPS_SCALE  # ~0.988 per frame at 24fps

# Audio FFT buffer: 256 frequency bins, computed from the last ~43ms of
# 24 kHz mono audio samples.
_AUDIO_HISTORY = 1024
_FFT_BINS = 256


_VERTEX_SHADER = """
#version 330
in vec2 in_pos;
void main() { gl_Position = vec4(in_pos, 0.0, 1.0); }
"""


_FRAGMENT_SHADER = """
#version 330
out vec4 fragColor;

uniform vec3      iResolution;
uniform float     iTime;
uniform float     iAudioAmp;    // 0..1 smoothed RMS of agent's outbound speech
uniform int       iState;       // 0 listening, 1 thinking, 2 speaking
uniform sampler2D iPrev;        // previous frame (ping-pong) — smoke trail source
uniform sampler2D iFFT;         // 256x1 audio FFT, row 0
uniform vec2      iParticles[3];

const float PI = 3.14159265;
const int   PARTICLE_COUNT = 3;
const float PARTICLE_SIZE = 0.20;
const float PARTICLE_EDGE_SMOOTHING = 0.003;
const float WALL_THINNESS = 60.0;

// Soft glowing disc with thin wall edges — directly from the original
// shader's getColor() but with a small audio-amp boost on the rim wobble.
float getColor(float dist, float angle, float size, float phase) {
    dist = dist
        + (sin(angle * 3.0 + iTime * 1.0 + phase) + 1.0) * 0.02
        + (cos(angle * 5.0 - iTime * 1.1 + phase) + 1.0) * 0.01;
    return pow(dist / size, WALL_THINNESS)
         * smoothstep(size, size - PARTICLE_EDGE_SMOOTHING, dist);
}

void main() {
    vec2 fragCoord = gl_FragCoord.xy;
    vec2 pixel = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;

    // Sample previous frame with a small vertical offset (upward smoke
    // drift) and decay multiplicatively — produces the trailing wisps.
    vec2 prevUV = (fragCoord + vec2(0.0, -0.7)) / iResolution.xy;
    vec3 mixedColor = texture(iPrev, prevUV).rgb;
    mixedColor *= TRAIL_DECAY;

    for (int i = 0; i < PARTICLE_COUNT; i++) {
        vec2 particle = iParticles[i];
        float dist = distance(particle, pixel);
        if (dist <= PARTICLE_SIZE) {
            vec2 delta = particle - pixel;
            float angle = atan(delta.x, delta.y);
            float phase = float(i);

            // Audio FFT modulates the particle's perceived radius per
            // angle — different frequency bins push out different sides.
            float fft = texture(iFFT, vec2(1.0 - (abs(angle) / PI), 0.33)).r;
            fft = fft + 0.1;
            dist += fft * 0.10 * (0.5 + 1.5 * iAudioAmp);

            // Chromatic aberration: render the same disc at three slightly
            // offset angles into R/G/B for an iridescent edge.
            mixedColor += vec3(
                getColor(dist, angle,        PARTICLE_SIZE, phase),
                getColor(dist, angle + 0.03, PARTICLE_SIZE, phase),
                getColor(dist, angle + 0.06, PARTICLE_SIZE, phase)
            ) * 0.10;
        }
    }

    // Alpha follows brightness so the form composites cleanly on dark UIs;
    // any LiveKit clients that ignore alpha just see RGB on a black field.
    float alpha = clamp(max(mixedColor.r, max(mixedColor.g, mixedColor.b)) * 1.4, 0.0, 1.0);
    fragColor = vec4(mixedColor, alpha);
}
"""


@dataclass
class _Particle:
    pos: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    vel: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))


class _ShaderRenderer:
    """Owns the moderngl context, ping-pong buffers, FFT texture, particles."""

    def __init__(self, size: int = CANVAS) -> None:
        self._size = size
        self._ctx = moderngl.create_standalone_context(backend="egl")

        # Substitute the per-frame trail-decay constant into the shader source.
        # The original uses a literal 0.995 at 60fps; we scale for 24fps.
        shader_src = _FRAGMENT_SHADER.replace(
            "TRAIL_DECAY", f"{_TRAIL_DECAY:.6f}"
        )
        self._prog = self._ctx.program(
            vertex_shader=_VERTEX_SHADER, fragment_shader=shader_src
        )

        verts = np.array([-1.0, -1.0, 3.0, -1.0, -1.0, 3.0], dtype="f4")
        self._vbo = self._ctx.buffer(verts.tobytes())
        self._vao = self._ctx.vertex_array(self._prog, [(self._vbo, "2f", "in_pos")])

        # Ping-pong textures for the smoke-trail feedback loop.
        self._tex_a = self._ctx.texture((size, size), 4)
        self._tex_b = self._ctx.texture((size, size), 4)
        for t in (self._tex_a, self._tex_b):
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
            t.repeat_x = False
            t.repeat_y = False
        self._fbo_a = self._ctx.framebuffer(color_attachments=[self._tex_a])
        self._fbo_b = self._ctx.framebuffer(color_attachments=[self._tex_b])
        self._fbo_a.use(); self._ctx.clear(0.0, 0.0, 0.0, 0.0)
        self._fbo_b.use(); self._ctx.clear(0.0, 0.0, 0.0, 0.0)
        self._render_to_a_next = True

        # Single-row R32F texture for FFT bins (256 wide, 1 tall).
        self._fft_tex = self._ctx.texture((_FFT_BINS, 1), 1, dtype="f4")
        self._fft_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._fft_tex.write(np.zeros(_FFT_BINS, dtype=np.float32).tobytes())

        self._prog["iResolution"].value = (float(size), float(size), 1.0)

        # Particle state — three slowly bouncing centers, slight wandering motion.
        rng = np.random.default_rng(42)
        self._particles = [
            _Particle(
                pos=rng.uniform(-0.15, 0.15, 2).astype(np.float32),
                vel=rng.uniform(-_MAX_VELOCITY, _MAX_VELOCITY, 2).astype(np.float32),
            )
            for _ in range(_PARTICLE_COUNT)
        ]
        self._rng = rng

        # Audio sample ring buffer (24 kHz mono int16 → float32).
        self._audio_history = np.zeros(_AUDIO_HISTORY, dtype=np.float32)
        self._fft_smoothed = np.zeros(_FFT_BINS, dtype=np.float32)
        self._window = np.hanning(_AUDIO_HISTORY).astype(np.float32)

    def push_audio_samples(self, samples_int16: np.ndarray) -> None:
        if samples_int16.size == 0:
            return
        f = samples_int16.astype(np.float32) / 32768.0
        n = f.size
        if n >= _AUDIO_HISTORY:
            self._audio_history = f[-_AUDIO_HISTORY:].copy()
        else:
            self._audio_history = np.roll(self._audio_history, -n)
            self._audio_history[-n:] = f

    def _step_particles(self) -> None:
        for p in self._particles:
            p.vel += self._rng.uniform(
                -_MAX_VELOCITY_CHANGE, _MAX_VELOCITY_CHANGE, 2
            ).astype(np.float32)
            p.vel -= p.pos * _FOCAL_POINT_TENDENCY
            np.clip(p.vel, -_MAX_VELOCITY, _MAX_VELOCITY, out=p.vel)
            pred = p.pos + p.vel
            if pred[0] < -0.5 or pred[0] > 0.5:
                p.vel[0] = -p.vel[0]
            if pred[1] < -0.5 or pred[1] > 0.5:
                p.vel[1] = -p.vel[1]
            p.pos += p.vel

    def _compute_fft(self) -> np.ndarray:
        windowed = self._audio_history * self._window
        spectrum = np.abs(np.fft.rfft(windowed))  # length = 513
        # log-magnitude → roughly [0, 1] perceptual scale
        scaled = np.log1p(spectrum) / 6.0
        # Resample 513 → 256 by mean-pooling adjacent pairs (drop one).
        usable = scaled[: 512].reshape(_FFT_BINS, 2).mean(axis=1)
        # Temporal smoothing so bins don't flicker frame-to-frame.
        self._fft_smoothed = 0.6 * self._fft_smoothed + 0.4 * usable
        return np.clip(self._fft_smoothed, 0.0, 1.0).astype(np.float32)

    def render(self, state: AnimationState, t: float) -> Image.Image:
        self._step_particles()
        fft_bins = self._compute_fft()
        self._fft_tex.write(fft_bins.tobytes())

        # Pack particle positions as a flat vec2 array.
        positions = np.array(
            [p.pos for p in self._particles], dtype=np.float32
        ).flatten()
        # Use .get(name) to tolerate uniforms the GLSL compiler may have
        # optimized away (e.g. if a uniform is declared but unreferenced).
        def _set(name: str, value) -> None:
            u = self._prog.get(name, None)
            if u is not None:
                u.value = value

        self._prog["iParticles"].write(positions.tobytes())
        _set("iTime", float(t))
        _set("iAudioAmp", float(state.amplitude))
        _set("iState", _STATE_CODE.get(state.semantic_state, 0))

        # Ping-pong: render to one FBO while sampling from the other.
        if self._render_to_a_next:
            target_fbo, prev_tex = self._fbo_a, self._tex_b
        else:
            target_fbo, prev_tex = self._fbo_b, self._tex_a
        self._render_to_a_next = not self._render_to_a_next

        prev_tex.use(location=1)
        self._fft_tex.use(location=2)
        self._prog["iPrev"].value = 1
        self._prog["iFFT"].value = 2

        target_fbo.use()
        self._vao.render(moderngl.TRIANGLES, vertices=3)
        raw = target_fbo.read(components=4)

        return Image.frombytes("RGBA", (self._size, self._size), raw).transpose(
            Image.FLIP_TOP_BOTTOM
        )


_renderer: _ShaderRenderer | None = None
_lock = threading.Lock()


def _get_renderer() -> _ShaderRenderer:
    global _renderer
    if _renderer is None:
        with _lock:
            if _renderer is None:
                _renderer = _ShaderRenderer()
    return _renderer


def render_frame(state: AnimationState, t: float) -> Image.Image:
    return _get_renderer().render(state, t)


def push_audio_samples(samples_int16: np.ndarray) -> None:
    _get_renderer().push_audio_samples(samples_int16)
