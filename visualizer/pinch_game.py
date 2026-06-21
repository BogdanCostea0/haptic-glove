#!/usr/bin/env python3
"""Pinch Grab Game — 2D gesture validation mini-game for the smart glove.

Sensor layout (after moving sensor from pinky to thumb):
  f[0] = index   f[1] = middle   f[2] = ring   f[3] = thumb
  v[0..3] = raw ADC voltage per finger (from updated firmware)

Pinch gesture: index AND thumb both normalised > PINCH_THRESH_NORM (0.0–1.0).
Normalisation uses per-finger flat_v/bent_v intervals from calibration.json
(run calibrate.py once to generate it).  Falls back to raw degrees if no file.

Cursor: IMU yaw/pitch mapped to screen position; in mock mode, follows the mouse.

Usage:
    python pinch_game.py --port COM3       # real glove
    python pinch_game.py --mock            # mouse + SPACE / LMB to pinch
    python pinch_game.py                   # auto-detect port, fall back to mock
"""

import sys
import math
import argparse
import random
import time
import json
import os

import pygame
from pygame.math import Vector2

sys.path.insert(0, ".")

try:
    from reader import SerialReader, GloveState, list_ports
    HAS_READER = True
except ImportError:
    HAS_READER = False

# ── Tuning ────────────────────────────────────────────────────────────────────

W, H          = 1024, 768
FPS_CAP       = 60
GAME_DURATION = 60       # seconds per round

PINCH_THRESH_NORM = 0.40  # 0.0–1.0 normalised bend — both index and thumb must exceed this
IMU_SENS      = 1200.0   # pixels per unit — body-X direction in world space → cursor

# f[] array order as sent by firmware: [index, middle, ring, little, thumb]
CHANNEL_TO_FINGER = ["index", "middle", "ring", "little", "thumb"]
CH_INDEX = 0
CH_THUMB = 4
COMBO_WINDOW  = 2.5      # seconds to maintain a combo streak
GRAB_COOLDOWN = 0.30     # minimum seconds between consecutive grabs
SPAWN_COUNT   = 5        # objects on screen at once

OBJ_RADIUS    = 36
GRAB_DIST     = OBJ_RADIUS + 14   # cursor-to-center distance to register a grab
CURSOR_R      = 15

# ── Colours ───────────────────────────────────────────────────────────────────

C_BG     = (10, 12, 20)
C_SCORE  = (255, 220, 80)
C_HUD    = (140, 140, 185)
C_TIMER  = (220, 90, 90)
C_OPEN   = (80, 200, 255)
C_PINCH  = (80, 255, 130)
C_NEAR   = (255, 230, 80)

C_OBJ = [
    (255, 90,  90),
    (100, 210, 255),
    (255, 200, 70),
    (190, 90,  255),
    (80,  255, 160),
    (255, 145, 50),
]

# ── Minimal GloveState fallback when reader.py isn't importable ───────────────

if not HAS_READER:
    class GloveState:  # type: ignore[no-redef]
        __slots__ = ("flex", "voltage", "quat", "button", "timestamp")
        def __init__(self):
            self.flex    = [0.0, 0.0, 0.0, 0.0]
            self.voltage = [0.0, 0.0, 0.0, 0.0]
            self.quat    = [1.0, 0.0, 0.0, 0.0]
            self.button  = False
            self.timestamp = 0

# ── Mock reader (mouse + keyboard) ───────────────────────────────────────────

class MockReader:
    """Simulates glove input with the mouse (position) and SPACE/LMB (pinch)."""

    connected  = True
    fps        = 60.0
    latency_ms = 0.0

    def __init__(self):
        self._pinching = False

    def start(self): pass
    def stop(self):  pass
    def send_haptic(self, _: int): pass  # no-op in mock mode

    def update(self):
        keys = pygame.key.get_pressed()
        mb   = pygame.mouse.get_pressed()
        self._pinching = bool(keys[pygame.K_SPACE] or mb[0])

    def latest(self):
        s = GloveState()
        val = 80.0 if self._pinching else 5.0
        s.flex    = [val, 5.0, 5.0, 5.0, val]   # index + thumb pinch; little mirrors ring
        s.voltage = [0.0, 0.0, 0.0, 0.0]   # no real voltage in mock mode
        s.quat    = [1.0, 0.0, 0.0, 0.0]
        s.button  = self._pinching
        return s

# ── Calibration ───────────────────────────────────────────────────────────────

def load_calibration() -> dict:
    path = os.path.join(os.path.dirname(__file__), "calibration.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        print(f"Loaded calibration.json ({list(data.keys())})")
        return data
    print("No calibration.json found — using raw degree fallback for pinch detection.")
    print("Run: python calibrate.py --port COM3")
    return {}

FINGER_NAMES_CALIB = ["index", "middle", "ring", "thumb"]

def normalize_finger(raw_deg: float, raw_volt: float, calib: dict, name: str) -> float:
    """Return normalised bend in [0.0, 1.0]: 0 = fully flat, 1 = fully bent.

    Priority: voltage-based interval (flat_v/bent_v) → degree-based (flat/bent)
    → raw degrees / 90 fallback.
    """
    c = calib.get(name)
    if c:
        if "flat_v" in c and raw_volt != 0.0:
            span = c["bent_v"] - c["flat_v"]
            if abs(span) > 1e-4:
                return max(0.0, min(1.0, (raw_volt - c["flat_v"]) / span))
        if "flat" in c and "bent" in c:
            span = c["bent"] - c["flat"]
            if abs(span) > 1e-4:
                return max(0.0, min(1.0, (raw_deg - c["flat"]) / span))
    return max(0.0, min(1.0, raw_deg / 90.0))

# ── Helpers ───────────────────────────────────────────────────────────────────

def finger_direction(q):
    """Return where the fingers point in world space.

    Sensor mounting: body-X → fingers, body-Y → opposite thumb, body-Z → through palm.
    Extracts the body-X axis (first column of rotation matrix) expressed in world frame.
    When fingers point at the screen, left/right tilting sweeps body-X through world-X,
    so horiz = world-X component (negated so tilting right moves cursor right).
    Vertical is unchanged: vert = world-Z component.
    """
    w, x, y, z = q
    # First column of rotation matrix = body-X in world frame
    horiz = 1 - 2*(y*y + z*z)       # world-X component of body-X
    vert  = 2*(x*z - w*y)           # world-Z component
    return horiz, vert


def fade_color(color, alpha_fraction):
    return tuple(int(c * alpha_fraction) for c in color)


def draw_circle_alpha(surf, color, center, radius, alpha):
    tmp = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
    pygame.draw.circle(tmp, (*color, alpha), (radius, radius), radius)
    surf.blit(tmp, (center[0]-radius, center[1]-radius))

# ── Game object ───────────────────────────────────────────────────────────────

class GrabObject:
    def __init__(self):
        self._spawn()
        self.grabbed = False
        self.grab_t  = 0.0

    def _spawn(self):
        margin = OBJ_RADIUS + 70
        self.pos    = Vector2(random.randint(margin, W - margin),
                              random.randint(margin + 80, H - margin - 60))
        self.color  = random.choice(C_OBJ)
        self.phase  = random.uniform(0, math.pi * 2)

    def reset(self):
        self._spawn()
        self.grabbed = False

    def draw(self, surf, t):
        cx, cy = int(self.pos.x), int(self.pos.y)

        if self.grabbed:
            age = t - self.grab_t
            r   = max(0, int(OBJ_RADIUS * (1 - age * 2.5)))
            if r > 0:
                draw_circle_alpha(surf, self.color, (cx, cy), r,
                                  max(0, int(255 * (1 - age * 3))))
            return

        r = OBJ_RADIUS + int(3 * math.sin(t * 2.8 + self.phase))

        # Soft glow
        draw_circle_alpha(surf, self.color, (cx, cy), r + 18, 35)
        draw_circle_alpha(surf, self.color, (cx, cy), r + 8,  60)

        # Body
        pygame.draw.circle(surf, self.color, (cx, cy), r)

        # Specular highlight
        hi = tuple(min(255, c + 90) for c in self.color)
        pygame.draw.circle(surf, hi, (cx - r//3, cy - r//3), r//4)

# ── Cursor ────────────────────────────────────────────────────────────────────

def draw_cursor(surf, pos, pinching, near_obj):
    cx, cy = int(pos.x), int(pos.y)
    color  = C_PINCH if pinching else (C_NEAR if near_obj else C_OPEN)

    # Glow ring when near or pinching
    if near_obj or pinching:
        draw_circle_alpha(surf, color, (cx, cy), CURSOR_R * 3, 30)
        draw_circle_alpha(surf, color, (cx, cy), CURSOR_R * 2, 50)

    # Three "finger" prongs
    spread = 0 if pinching else 12
    for base_angle in (30, 150, 270):
        a  = math.radians(base_angle + spread)
        x1 = cx + int(CURSOR_R * 0.45 * math.cos(a))
        y1 = cy + int(CURSOR_R * 0.45 * math.sin(a))
        x2 = cx + int(CURSOR_R * 1.55 * math.cos(a))
        y2 = cy + int(CURSOR_R * 1.55 * math.sin(a))
        pygame.draw.line(surf, color, (x1, y1), (x2, y2), 3)

    pygame.draw.circle(surf, color, (cx, cy), CURSOR_R, 2)
    if pinching:
        pygame.draw.circle(surf, color, (cx, cy), CURSOR_R // 2)

# ── HUD ───────────────────────────────────────────────────────────────────────

def draw_hud(surf, fonts, score, combo, time_left, pinching, connected,
             mock_mode, fps, latency_ms, flex, norm_flex):
    f_sm, f_med, f_big = fonts

    # Score (centered top)
    sc_surf = f_big.render(str(score), True, C_SCORE)
    surf.blit(sc_surf, (W // 2 - sc_surf.get_width() // 2, 10))
    lbl = f_med.render("score", True, C_HUD)
    surf.blit(lbl, (W // 2 - lbl.get_width() // 2, 62))

    # Combo streak
    if combo > 1:
        combo_col = (255, 200, 60) if combo < 5 else (255, 100, 60)
        cs = f_med.render(f"×{combo} combo!", True, combo_col)
        surf.blit(cs, (W // 2 - cs.get_width() // 2, 86))

    # Timer (top-right)
    secs  = int(time_left)
    t_col = C_TIMER if secs <= 10 else C_HUD
    ts    = f_med.render(f"{secs:02d}s", True, t_col)
    surf.blit(ts, (W - ts.get_width() - 16, 16))

    # Flex bars — f[0]=index f[1]=middle f[2]=ring f[3]=little f[4]=thumb
    labels     = ["IDX", "MID", "RNG", "LIT", "TMB"]
    bar_colors = [C_OPEN, (110, 210, 110), (210, 160, 110), (180, 130, 80), C_PINCH]
    bar_w, bar_h = 32, 72
    gap          = 10
    total_w      = 5 * bar_w + 4 * gap
    bx           = (W - total_w) // 2
    by           = H - bar_h - 28

    for i in range(5):
        norm = norm_flex[i]                          # 0.0 (flat) … 1.0 (bent)
        fill = int(norm * bar_h)
        col  = bar_colors[i]
        x    = bx + i * (bar_w + gap)

        bg_col = (40, 28, 42) if i in (CH_THUMB, CH_INDEX) else (28, 28, 42)
        pygame.draw.rect(surf, bg_col, (x, by, bar_w, bar_h))
        if fill:
            pygame.draw.rect(surf, col, (x, by + bar_h - fill, bar_w, fill))

        # Draw threshold line for the two pinch fingers
        if i in (CH_THUMB, CH_INDEX):
            ty = by + bar_h - int(PINCH_THRESH_NORM * bar_h)
            pygame.draw.line(surf, (255, 255, 100), (x, ty), (x + bar_w, ty), 1)

        pygame.draw.rect(surf, (55, 55, 85), (x, by, bar_w, bar_h), 1)

        l = f_sm.render(labels[i], True, C_HUD)
        surf.blit(l, (x + bar_w // 2 - l.get_width() // 2, by + bar_h + 3))
        d = f_sm.render(f"{int(norm * 100)}%", True, col)
        surf.blit(d, (x + bar_w // 2 - d.get_width() // 2, by - 17))

    # Pinch indicator (bottom-right)
    pcol = C_PINCH if pinching else (55, 55, 75)
    pygame.draw.circle(surf, pcol, (W - 50, H - 50), 28)
    pl = f_sm.render("PINCH", True, (0,0,0) if pinching else (80,80,100))
    surf.blit(pl, (W - 50 - pl.get_width() // 2, H - 50 - pl.get_height() // 2))

    # Connection status (top-left)
    if mock_mode:
        dot_col = (100, 200, 100)
        status  = "MOCK"
    elif connected:
        dot_col = (100, 200, 100)
        status  = "GLOVE"
    else:
        dot_col = (220, 80, 80)
        status  = "SEARCHING…"

    pygame.draw.circle(surf, dot_col, (12, 12), 6)
    surf.blit(f_sm.render(status, True, dot_col), (24, 5))
    if not mock_mode:
        fl = f_sm.render(f"FPS {fps:.0f}  lat {latency_ms:.1f}ms", True, C_HUD)
        surf.blit(fl, (24, 20))

    # Controls hint (very bottom)
    hint = f_sm.render("SPACE / LMB = pinch   R = reset cursor   ESC = quit", True, (50, 50, 75))
    surf.blit(hint, (W // 2 - hint.get_width() // 2, H - 14))

# ── Game-over overlay ─────────────────────────────────────────────────────────

def draw_game_over(surf, fonts, score):
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 170))
    surf.blit(overlay, (0, 0))

    f_sm, f_med, f_big = fonts
    f_xl = pygame.font.SysFont("consolas", 64)

    t1 = f_xl.render("TIME'S UP", True, C_SCORE)
    t2 = f_med.render(f"Final score: {score}", True, (255, 255, 255))
    t3 = f_sm.render("ENTER — play again    ESC — quit", True, C_HUD)

    surf.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 100))
    surf.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 - 10))
    surf.blit(t3, (W // 2 - t3.get_width() // 2, H // 2 + 60))

# ── Main game loop ────────────────────────────────────────────────────────────

def run_game(reader, mock_mode, calib: dict):
    pygame.init()
    surf  = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Pinch Grab — Glove Gesture Validator")
    clock = pygame.time.Clock()

    # Hide system cursor in glove mode (cursor is drawn by us)
    pygame.mouse.set_visible(mock_mode)

    fonts = (
        pygame.font.SysFont("consolas", 14),
        pygame.font.SysFont("consolas", 22),
        pygame.font.SysFont("consolas", 48),
    )
    f_sm = fonts[0]
    score_pop_font = pygame.font.SysFont("consolas", 30)

    def new_game():
        return {
            "objects":    [GrabObject() for _ in range(SPAWN_COUNT)],
            "score":      0,
            "combo":      0,
            "last_grab":  0.0,
            "game_end":   time.monotonic() + GAME_DURATION,
            "pops":       [],   # list of (pos, t_created, color)
            "over":       False,
        }

    g = new_game()

    cursor_pos  = Vector2(W / 2, H / 2)
    ref_horiz   = 0.0
    ref_vert    = 0.0
    was_pinch   = False
    state       = GloveState()

    reader.start()

    running = True
    while running:
        t_now = time.monotonic()
        clock.tick(FPS_CAP)

        time_left = max(0.0, g["game_end"] - t_now)

        # ── Events ───────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    ref_horiz, ref_vert = finger_direction(state.quat)
                    cursor_pos = Vector2(W / 2, H / 2)
                elif event.key == pygame.K_RETURN and g["over"]:
                    g = new_game()

        # ── Reader update ────────────────────────────────────────────────────
        if mock_mode:
            reader.update()

        fresh = reader.latest()
        if fresh:
            state = fresh

        flex    = state.flex     # [index, middle, ring, thumb] in degrees
        voltage = state.voltage  # [index, middle, ring, thumb] in volts

        # Normalised bend [0.0 flat … 1.0 bent] using per-finger calib intervals
        # voltage has 4 entries (no sensor on little); little borrows ring's voltage
        vol_lookup = [voltage[0], voltage[1], voltage[2], voltage[2], voltage[3]]
        norm_flex = [
            normalize_finger(flex[i], vol_lookup[i], calib, CHANNEL_TO_FINGER[i])
            for i in range(5)
        ]

        # ── Cursor ───────────────────────────────────────────────────────────
        if mock_mode:
            cursor_pos = Vector2(pygame.mouse.get_pos())
        else:
            horiz, vert = finger_direction(state.quat)
            dx =  (horiz - ref_horiz) * IMU_SENS
            dy =  (vert  - ref_vert)  * IMU_SENS
            cursor_pos = Vector2(
                max(0.0, min(float(W), W / 2.0 + dx)),
                max(0.0, min(float(H), H / 2.0 + dy)),
            )

        # ── Pinch detection (normalised) ─────────────────────────────────────
        index_bent = norm_flex[CH_INDEX] > PINCH_THRESH_NORM
        thumb_bent = norm_flex[CH_THUMB] > PINCH_THRESH_NORM
        pinching   = index_bent and thumb_bent
        just_pinch = pinching and not was_pinch

        # ── Grab logic ───────────────────────────────────────────────────────
        near_any = False
        if not g["over"] and time_left > 0:
            for obj in g["objects"]:
                if obj.grabbed:
                    continue
                dist = (cursor_pos - obj.pos).length()
                if dist < GRAB_DIST + OBJ_RADIUS * 0.5:
                    near_any = True
                if just_pinch and dist < GRAB_DIST and (t_now - g["last_grab"]) > GRAB_COOLDOWN:
                    obj.grabbed = True
                    obj.grab_t  = t_now
                    g["last_grab"] = t_now
                    g["score"]    += 1
                    g["combo"]    += 1
                    g["pops"].append((Vector2(obj.pos), t_now, obj.color))
                    reader.send_haptic(1)   # strong click on successful grab

        was_pinch = pinching

        # Respawn grabbed objects after shrink animation
        for obj in g["objects"]:
            if obj.grabbed and (t_now - obj.grab_t) > 0.4:
                obj.reset()

        # Expire old pops
        g["pops"] = [(p, tc, c) for p, tc, c in g["pops"] if t_now - tc < 0.7]

        # Reset combo after idle window
        if (t_now - g["last_grab"]) > COMBO_WINDOW and g["combo"] > 0:
            g["combo"] = 0

        # Detect game over
        if time_left <= 0 and not g["over"]:
            g["over"] = True
            reader.send_haptic(14)  # double click on game over

        # ── Draw ─────────────────────────────────────────────────────────────
        surf.fill(C_BG)

        for obj in g["objects"]:
            obj.draw(surf, t_now)

        # Score pop-ups
        for pos, tc, color in g["pops"]:
            age   = t_now - tc
            frac  = max(0.0, 1.0 - age * 1.8)
            y_off = int(age * 70)
            txt   = score_pop_font.render("+1", True, fade_color(color, frac))
            surf.blit(txt, (int(pos.x) - txt.get_width() // 2,
                            int(pos.y) - 30 - y_off))

        draw_cursor(surf, cursor_pos, pinching, near_any)

        draw_hud(surf, fonts, g["score"], g["combo"], time_left,
                 pinching, getattr(reader, "connected", True),
                 mock_mode, getattr(reader, "fps", 60.0),
                 getattr(reader, "latency_ms", 0.0), flex, norm_flex)

        if g["over"]:
            draw_game_over(surf, fonts, g["score"])

        pygame.display.flip()

    reader.stop()
    pygame.quit()

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global PINCH_THRESH_NORM
    ap = argparse.ArgumentParser(description="Pinch Grab — VR Glove Gesture Validator")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--port", help="Serial port, e.g. COM3")
    grp.add_argument("--mock", action="store_true",
                     help="Mouse position + SPACE/LMB to pinch (no glove needed)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--thresh", type=float, default=PINCH_THRESH_NORM,
                    help=f"Normalised pinch threshold 0.0–1.0 (default {PINCH_THRESH_NORM})")
    args = ap.parse_args()

    PINCH_THRESH_NORM = args.thresh
    calib = load_calibration()

    if args.mock:
        run_game(MockReader(), mock_mode=True, calib=calib)
        return

    if args.port:
        if not HAS_READER:
            print("pyserial not installed — run: pip install pyserial")
            sys.exit(1)
        run_game(SerialReader(args.port, args.baud), mock_mode=False, calib=calib)
        return

    # No flag given — try to auto-detect a port, fall back to mock
    if HAS_READER:
        try:
            ports = list_ports()
        except Exception:
            ports = []
        if ports:
            print(f"Auto-selected serial port: {ports[0]}")
            run_game(SerialReader(ports[0], args.baud), mock_mode=False, calib=calib)
            return

    print("No serial port found or pyserial unavailable — starting in mock mode.")
    print("  Mouse = hand position,  SPACE / LMB = pinch gesture")
    run_game(MockReader(), mock_mode=True, calib=calib)


if __name__ == "__main__":
    main()
