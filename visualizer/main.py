#!/usr/bin/env python3
"""VR Glove 3D Visualizer

Usage:
    python main.py                  # auto-selects the only available COM port
    python main.py --port COM3

Controls:
    R      – reset orientation reference (zeros the current IMU pose)
    F      – toggle XYZ axis display
    H      – send haptic test buzz (effect 1)
    ESC    – quit
"""

import sys
import math
import argparse
import json
import os

import pygame
from pygame.locals import (DOUBLEBUF, OPENGL, QUIT,
                            KEYDOWN, K_ESCAPE, K_r, K_f, K_h)
from OpenGL.GL import *
from OpenGL.GLU import *

from reader import SerialReader, GloveState, list_ports
from hand import (draw_hand, draw_axes, quat_to_gl_matrix,
                  quat_relative, FINGER_NAMES)

# ── Layout ────────────────────────────────────────────────────────────────────
W, H    = 1200, 800
FPS_CAP = 60

FINGER_BAR_COLORS = [
    (0.30, 0.70, 1.00),   # index  – blue
    (0.30, 1.00, 0.55),   # middle – green
    (1.00, 0.70, 0.25),   # ring   – orange
    (0.85, 0.55, 0.20),   # little – dark orange (mirrors ring)
    (1.00, 0.38, 0.38),   # thumb  – red
]
BAR_W      = 80
BAR_H_MAX  = 120
BAR_GAP    = 20

# ── Font helpers ───────────────────────────────────────────────────────────────
_fonts: dict = {}


def _font(size: int) -> pygame.font.Font:
    if size not in _fonts:
        _fonts[size] = pygame.font.SysFont("consolas", size)
    return _fonts[size]


def draw_text(text: str, x: int, y: int, color=(255, 255, 255), size: int = 16):
    """Blit pygame text into the OpenGL framebuffer at window-space (x, y)."""
    surf = _font(size).render(text, True, color)
    data = pygame.image.tostring(surf, "RGBA", True)
    glWindowPos2i(x, y)
    glDrawPixels(surf.get_width(), surf.get_height(),
                 GL_RGBA, GL_UNSIGNED_BYTE, data)


# ── 2-D overlay helpers ───────────────────────────────────────────────────────
def _begin_2d():
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(0, W, 0, H, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)


def _end_2d():
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()


def _circle_2d(cx, cy, r, filled=True, segments=32):
    mode = GL_TRIANGLE_FAN if filled else GL_LINE_LOOP
    glBegin(mode)
    if filled:
        glVertex2f(cx, cy)
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
    glEnd()


# ── Overlay widgets ───────────────────────────────────────────────────────────
def draw_finger_bars(flex_degs: list, flex_volts: list, calib: dict):
    n = len(FINGER_NAMES)
    total_w = n * BAR_W + (n - 1) * BAR_GAP
    x0 = (W - total_w) // 2
    y0 = 20

    # voltage has 4 entries [index, middle, ring, thumb]; little borrows ring
    _volt_idx = [0, 1, 2, 2, 3]

    for i, name in enumerate(FINGER_NAMES):
        raw  = flex_degs[i] if i < len(flex_degs) else 0.0
        vi   = _volt_idx[i] if i < len(_volt_idx) else None
        volt = flex_volts[vi] if (flex_volts and vi is not None and vi < len(flex_volts)) else None

        # Normalise using per-finger voltage interval from calibration
        key = name.lower()
        if calib and key in calib:
            c = calib[key]
            if "flat_v" in c and volt is not None:
                span = c["bent_v"] - c["flat_v"]
                norm = (volt - c["flat_v"]) / span * 180.0 if span else raw
            elif "bent" in c and "flat" in c:
                span = c["bent"] - c["flat"]
                norm = (raw - c["flat"]) / span * 180.0 if span else raw
            else:
                norm = raw
        else:
            norm = raw
        norm = max(0.0, min(180.0, norm))
        fill = int(norm / 180.0 * BAR_H_MAX)

        x = x0 + i * (BAR_W + BAR_GAP)

        # Background slot
        glColor3f(0.14, 0.14, 0.18)
        glRectf(x, y0, x + BAR_W, y0 + BAR_H_MAX)

        # Filled bar
        r, g, b = FINGER_BAR_COLORS[i]
        glColor3f(r * 0.4, g * 0.4, b * 0.4)        # dark tint at bottom
        glRectf(x, y0, x + BAR_W, y0 + fill // 2)
        glColor3f(r, g, b)
        glRectf(x, y0 + fill // 2, x + BAR_W, y0 + fill)

        # Border
        glColor3f(0.40, 0.40, 0.50)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x,          y0)
        glVertex2f(x + BAR_W,  y0)
        glVertex2f(x + BAR_W,  y0 + BAR_H_MAX)
        glVertex2f(x,          y0 + BAR_H_MAX)
        glEnd()

        # Name + angle text
        draw_text(name[:3], x + 4, y0 + BAR_H_MAX + 4,
                  color=(160, 160, 200), size=13)
        draw_text(f"{raw:.0f}°", x + 4, y0 + BAR_H_MAX + 20,
                  color=(230, 230, 255), size=13)


def draw_button_indicator(pressed: bool):
    cx, cy, r = W - 90, H - 90, 36
    if pressed:
        glColor3f(0.15, 1.0, 0.25)
        _circle_2d(cx, cy, r)
        draw_text("GRAB", cx - 22, cy - 9, color=(0, 0, 0), size=16)
    else:
        glColor3f(0.20, 0.20, 0.25)
        _circle_2d(cx, cy, r)
        glColor3f(0.40, 0.40, 0.50)
        _circle_2d(cx, cy, r, filled=False)
        draw_text("GRAB", cx - 22, cy - 9, color=(90, 90, 110), size=16)


def draw_stats(reader, show_axes: bool):
    dot_color = (80, 220, 80) if reader.connected else (220, 80, 80)
    status    = "CONNECTED" if reader.connected else "SEARCHING..."

    glColor3f(*[c / 255 for c in dot_color])
    _circle_2d(18, H - 18, 7)
    draw_text(status, 32, H - 26, color=dot_color, size=14)
    draw_text(f"FPS {reader.fps:.0f}   latency {reader.latency_ms:.1f} ms",
              14, H - 46, color=(160, 160, 190), size=13)

    # Hints bottom-right
    hints = ["R – reset orientation", "F – toggle axes",
             "H – haptic test",       "ESC – quit"]
    for i, h in enumerate(hints):
        draw_text(h, W - 210, 20 + i * 18, color=(90, 90, 120), size=13)

    ax_label = "axes: ON " if show_axes else "axes: OFF"
    draw_text(ax_label, W - 210, 92, color=(90, 90, 120), size=13)


# ── 3-D scene ─────────────────────────────────────────────────────────────────
def draw_grid():
    glDisable(GL_LIGHTING)
    glColor3f(0.17, 0.17, 0.26)
    glLineWidth(1.0)
    glBegin(GL_LINES)
    for i in range(-6, 7):
        glVertex3f(i * 0.5, -1.5, -3.0); glVertex3f(i * 0.5, -1.5,  3.0)
        glVertex3f(-3.0, -1.5, i * 0.5); glVertex3f( 3.0, -1.5, i * 0.5)
    glEnd()
    glEnable(GL_LIGHTING)


def setup_opengl():
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)

    glLightfv(GL_LIGHT0, GL_POSITION, (3.0,  5.0,  4.0,  1.0))
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  (1.0,  1.0,  1.0,  1.0))
    glLightfv(GL_LIGHT0, GL_AMBIENT,  (0.25, 0.25, 0.25, 1.0))
    glLightfv(GL_LIGHT0, GL_SPECULAR, (0.40, 0.40, 0.40, 1.0))
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR,  (0.3, 0.3, 0.3, 1.0))
    glMaterialf (GL_FRONT_AND_BACK, GL_SHININESS, 32.0)

    glClearColor(0.07, 0.07, 0.11, 1.0)

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45.0, W / H, 0.1, 100.0)
    glMatrixMode(GL_MODELVIEW)


def render_frame(state: GloveState, ref_quat: list,
                 show_axes: bool, reader, calib: dict):
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()

    gluLookAt(0.0, 1.0, 4.5,    # eye position
              0.0, 0.2, 0.0,    # look-at point
              0.0, 1.0, 0.0)    # up vector

    draw_grid()

    # Rotate the hand by the IMU quaternion (relative to reference pose)
    rel = quat_relative(ref_quat, state.quat)
    glMultMatrixf(quat_to_gl_matrix(*rel))

    draw_hand(state.flex)
    if show_axes:
        draw_axes(1.2)

    # 2-D overlay — no depth test, no lighting
    _begin_2d()
    draw_finger_bars(state.flex, state.voltage, calib)
    draw_button_indicator(state.button)
    draw_stats(reader, show_axes)
    _end_2d()


# ── Startup helpers ───────────────────────────────────────────────────────────
def pick_port() -> str:
    ports = list_ports()
    if not ports:
        print("No serial ports found. Plug in the glove and try again.")
        sys.exit(1)
    if len(ports) == 1:
        print(f"Auto-selected: {ports[0]}")
        return ports[0]
    print("Available ports:")
    for i, p in enumerate(ports):
        print(f"  {i}: {p}")
    idx = int(input("Select port number: "))
    return ports[idx]


def load_calibration() -> dict:
    path = os.path.join(os.path.dirname(__file__), "calibration.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        print(f"Loaded calibration.json ({list(data.keys())})")
        return data
    return {}


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="VR Glove Visualizer")
    ap.add_argument("--port", help="Serial port, e.g. COM3")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    port  = args.port or pick_port()
    calib = load_calibration()

    pygame.init()
    pygame.display.set_caption("VR Glove Visualizer")
    pygame.display.set_mode((W, H), DOUBLEBUF | OPENGL)
    clock = pygame.time.Clock()

    setup_opengl()

    reader = SerialReader(port, args.baud)
    reader.start()
    print(f"Connecting to {port} @ {args.baud} …  (R=reset orientation, F=axes, ESC=quit)")

    state     = GloveState()
    ref_quat  = [1.0, 0.0, 0.0, 0.0]
    show_axes = True   # on by default so the user can immediately see IMU axes

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
                elif event.key == K_r:
                    ref_quat = list(state.quat)
                    print("Orientation reference reset.")
                elif event.key == K_f:
                    show_axes = not show_axes
                elif event.key == K_h:
                    reader.send_haptic(1)
                    print("Haptic test: effect 1")

        fresh = reader.latest()
        if fresh:
            state = fresh

        render_frame(state, ref_quat, show_axes, reader, calib)
        pygame.display.flip()
        clock.tick(FPS_CAP)

    reader.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
