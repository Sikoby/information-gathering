"""Render a single animated face frame for the agent.

Pure functions only — no I/O, no LiveKit, no asyncio. Easy to unit-test by
calling `render_frame(...)` and saving the result to disk.

The visual: a soft circular "consultant orb" centered on a transparent canvas.
Three states drive the look:
  - listening: muted navy, slow idle breath
  - thinking: desaturated, a thin arc rotates around the perimeter
  - speaking: brighter accent color, ring radius and an inner waveform modulated
              by `amplitude` (0.0 - 1.0)
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter

SemanticState = Literal["initializing", "idle", "listening", "thinking", "speaking"]


@dataclass
class AnimationState:
    semantic_state: SemanticState = "listening"
    amplitude: float = 0.0


CANVAS = 256
CENTER = CANVAS // 2


def _hsl(h_deg: float, s_pct: float, l_pct: float, a: int = 255) -> tuple[int, int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h_deg / 360.0, l_pct / 100.0, s_pct / 100.0)
    return int(r * 255), int(g * 255), int(b * 255), a


# Mirrors frontend/src/index.css tokens so the orb visually belongs to the dashboard.
_PRIMARY = _hsl(222.2, 47.4, 11.2)
_MUTED = _hsl(215.4, 16.3, 46.9)
_SUCCESS = _hsl(142.1, 76.2, 36.3)
_ACCENT_SPEAK = _hsl(217, 91, 60)  # brighter blue for the speaking ring


def _palette(state: SemanticState, amplitude: float) -> tuple[
    tuple[int, int, int, int],
    tuple[int, int, int, int],
]:
    if state == "speaking":
        return _ACCENT_SPEAK, _PRIMARY
    if state == "thinking":
        return _MUTED, _PRIMARY
    if state in ("initializing", "idle"):
        return _MUTED, _MUTED
    return _PRIMARY, _PRIMARY  # listening


def render_frame(state: AnimationState, t: float) -> Image.Image:
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    ring_color, core_color = _palette(state.semantic_state, state.amplitude)

    base_radius = 70.0
    if state.semantic_state == "speaking":
        pulse = base_radius + 22.0 * min(1.0, state.amplitude * 1.5)
    elif state.semantic_state == "listening":
        pulse = base_radius + 3.0 * math.sin(t * 1.6)
    elif state.semantic_state == "thinking":
        pulse = base_radius + 2.0 * math.sin(t * 0.8)
    else:
        pulse = base_radius

    glow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    glow_r = pulse + 18.0
    gd.ellipse(
        (CENTER - glow_r, CENTER - glow_r, CENTER + glow_r, CENTER + glow_r),
        fill=(*ring_color[:3], 70),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=12))
    img.alpha_composite(glow)

    draw.ellipse(
        (CENTER - pulse, CENTER - pulse, CENTER + pulse, CENTER + pulse),
        fill=core_color,
    )

    inner_r = pulse - 6.0
    if inner_r > 0:
        draw.ellipse(
            (CENTER - inner_r, CENTER - inner_r, CENTER + inner_r, CENTER + inner_r),
            outline=ring_color,
            width=3,
        )

    if state.semantic_state == "thinking":
        arc_r = pulse + 10.0
        sweep_start = (t * 180.0) % 360.0
        sweep_end = (sweep_start + 60.0) % 360.0
        if sweep_end < sweep_start:
            draw.arc(
                (CENTER - arc_r, CENTER - arc_r, CENTER + arc_r, CENTER + arc_r),
                start=sweep_start, end=360.0, fill=_SUCCESS, width=3,
            )
            draw.arc(
                (CENTER - arc_r, CENTER - arc_r, CENTER + arc_r, CENTER + arc_r),
                start=0.0, end=sweep_end, fill=_SUCCESS, width=3,
            )
        else:
            draw.arc(
                (CENTER - arc_r, CENTER - arc_r, CENTER + arc_r, CENTER + arc_r),
                start=sweep_start, end=sweep_end, fill=_SUCCESS, width=3,
            )

    if state.semantic_state == "speaking" and state.amplitude > 0.02:
        wave_amp = 18.0 * min(1.0, state.amplitude * 1.5)
        bars = 9
        spacing = 9
        total_w = (bars - 1) * spacing
        x0 = CENTER - total_w / 2
        for i in range(bars):
            phase = t * 6.0 + i * 0.7
            h = wave_amp * (0.45 + 0.55 * abs(math.sin(phase)))
            x = x0 + i * spacing
            draw.rounded_rectangle(
                (x - 2, CENTER - h, x + 2, CENTER + h),
                radius=2,
                fill=(*ring_color[:3], 220),
            )

    return img
