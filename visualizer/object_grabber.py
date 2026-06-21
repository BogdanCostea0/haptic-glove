#!/usr/bin/env python3
"""Object Grabber — pick-and-place gesture minigame for the VR smart glove.

Pick up colored objects from the left panel and drop them onto the matching
colored target zone on the right. Score 10 points per correct placement.

Controls:
    Pinch (index + thumb) — grab nearest object / release held object
    Hand tilt             — move cursor
    R                     — reset cursor to center
    ESC                   — quit
    ENTER (game over)     — play again

Usage:
    python object_grabber.py --port COM3
    python object_grabber.py --mock
    python object_grabber.py          # auto-detect port, fallback to mock
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
W, H           = 1024, 768
FPS_CAP        = 60
GAME_DURATION  = 90

PINCH_THRESH_NORM = 0.40
IMU_SENS          = 1200.0
GRAB_COOLDOWN     = 0.25

OBJ_R     = 36
TARGET_R  = 54
CURSOR_R  = 14
GRAB_DIST = OBJ_R + CURSOR_R + 10

CH_INDEX = 0
CH_THUMB = 4
CHANNEL_TO_FINGER = ["index", "middle", "ring", "little", "thumb"]

MAX_OBJECTS = 3   # objects in spawn area at once

# ── Colors ────────────────────────────────────────────────────────────────────
C_BG    = (10,  12,  20)
C_HUD   = (140, 140, 185)
C_SCORE = (255, 220, 80)
C_TIMER = (220, 90,  90)
C_OPEN  = (80,  200, 255)
C_PINCH = (80,  255, 130)
C_SPAWN = (22,  26,  45)

# (label, bright_color, dim_color)
TYPES = [
    ("R", (255,  80,  80),  (110, 28,  28)),
    ("B", ( 70, 140, 255),  ( 25, 55, 120)),
    ("G", ( 70, 215,  95),  ( 25, 88,  38)),
    ("Y", (255, 210,  45),  (110, 88,  15)),
]

# Fixed spawn slots in the left panel (no overlap guaranteed)
SPAWN_PANEL = pygame.Rect(55, 110, 190, 548)
SPAWN_SLOTS = [
    Vector2(150, 230),
    Vector2(150, 384),
    Vector2(150, 538),
]

# Target zone positions — right half of the screen
TARGET_POSITIONS = [
    Vector2(810, 165),
    Vector2(940, 370),
    Vector2(810, 575),
    Vector2(670, 370),
]

# ── Calibration ───────────────────────────────────────────────────────────────
def load_calibration() -> dict:
    path = os.path.join(os.path.dirname(__file__), "calibration.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def normalize_finger(raw_deg: float, raw_volt: float, calib: dict, name: str) -> float:
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


# ── IMU cursor (same axis mapping as pinch_game) ──────────────────────────────
def finger_direction(q):
    w, x, y, z = q
    horiz = 1 - 2*(y*y + z*z)   # world-X component of body-X
    vert  = 2*(x*z - w*y)        # world-Z component of body-X
    return horiz, vert


# ── Mock glove state (used when HAS_READER is False) ─────────────────────────
if not HAS_READER:
    class GloveState:  # type: ignore[no-redef]
        __slots__ = ("flex", "voltage", "quat", "button", "timestamp")
        def __init__(self):
            self.flex      = [0.0] * 5
            self.voltage   = [0.0] * 4
            self.quat      = [1.0, 0.0, 0.0, 0.0]
            self.button    = False
            self.timestamp = 0


class MockReader:
    connected  = True
    fps        = 60.0
    latency_ms = 0.0

    def __init__(self):          self._pinching = False
    def start(self):             pass
    def stop(self):              pass
    def send_haptic(self, _):    pass

    def update(self):
        keys = pygame.key.get_pressed()
        mb   = pygame.mouse.get_pressed()
        self._pinching = bool(keys[pygame.K_SPACE] or mb[0])

    def latest(self):
        s = GloveState()
        v = 80.0 if self._pinching else 5.0
        s.flex = [v, 5.0, 5.0, 5.0, v]
        s.quat = [1.0, 0.0, 0.0, 0.0]
        return s


# ── Drawing helpers ───────────────────────────────────────────────────────────
def draw_circle_alpha(surf, color, center, radius, alpha):
    if alpha <= 0 or radius <= 0:
        return
    tmp = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(tmp, (*color, int(alpha)), (radius, radius), radius)
    surf.blit(tmp, (int(center[0]) - radius, int(center[1]) - radius))


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ── Game entities ─────────────────────────────────────────────────────────────
class GrabObject:
    def __init__(self, slot_idx: int, type_idx: int = None):
        self.slot_idx  = slot_idx
        self.type_idx  = type_idx if type_idx is not None else random.randint(0, len(TYPES) - 1)
        self.label, self.color, self.dim = TYPES[self.type_idx]
        self.pos  = Vector2(SPAWN_SLOTS[slot_idx])
        self.held = False

    def snap_to_spawn(self):
        self.pos  = Vector2(SPAWN_SLOTS[self.slot_idx])
        self.held = False

    def draw(self, surf, font, cursor_near: bool):
        cx, cy = int(self.pos.x), int(self.pos.y)
        col    = self.color

        if self.held:
            draw_circle_alpha(surf, col, (cx, cy), OBJ_R + 24, 55)
        elif cursor_near:
            draw_circle_alpha(surf, col, (cx, cy), OBJ_R + 18, 40)
            draw_circle_alpha(surf, col, (cx, cy), OBJ_R + 8,  65)

        pygame.draw.circle(surf, col, (cx, cy), OBJ_R)
        hi = tuple(min(255, c + 80) for c in col)
        pygame.draw.circle(surf, hi, (cx - OBJ_R // 3, cy - OBJ_R // 3), OBJ_R // 4)

        lbl = font.render(self.label, True, (10, 10, 10))
        surf.blit(lbl, (cx - lbl.get_width() // 2, cy - lbl.get_height() // 2))


class TargetZone:
    def __init__(self, type_idx: int, pos: Vector2):
        self.type_idx           = type_idx
        self.pos                = Vector2(pos)
        self.label, self.color, self.dim = TYPES[type_idx]
        self.count              = 0
        self.flash_t            = -99.0

    def trigger_flash(self, t):
        self.flash_t = t
        self.count  += 1

    def accepts(self, obj: GrabObject) -> bool:
        return obj.type_idx == self.type_idx

    def cursor_in_range(self, pos: Vector2) -> bool:
        return (pos - self.pos).length() < TARGET_R + OBJ_R // 2

    def draw(self, surf, f_label, f_count, t):
        cx, cy = int(self.pos.x), int(self.pos.y)
        age    = t - self.flash_t
        flash  = max(0.0, 1.0 - age * 2.5)

        if flash > 0:
            glow = lerp_color(self.color, (255, 255, 255), flash * 0.35)
            draw_circle_alpha(surf, glow, (cx, cy), TARGET_R + 22, int(flash * 110))

        ring_col = lerp_color(self.dim, self.color, 0.55 + flash * 0.45)
        pygame.draw.circle(surf, ring_col, (cx, cy), TARGET_R, 4)

        lbl = f_label.render(self.label, True, ring_col)
        surf.blit(lbl, (cx - lbl.get_width() // 2, cy - lbl.get_height() // 2 - 8))

        if self.count > 0:
            cnt = f_count.render(f"x{self.count}", True, self.color)
            surf.blit(cnt, (cx - cnt.get_width() // 2, cy + 12))


# ── Cursor ────────────────────────────────────────────────────────────────────
def draw_cursor(surf, pos, pinching, near_obj):
    cx, cy = int(pos.x), int(pos.y)
    color  = C_PINCH if pinching else ((255, 230, 80) if near_obj else C_OPEN)

    if pinching or near_obj:
        draw_circle_alpha(surf, color, (cx, cy), CURSOR_R * 3, 28)
        draw_circle_alpha(surf, color, (cx, cy), CURSOR_R * 2, 52)

    spread = 0 if pinching else 12
    for base in (30, 150, 270):
        a  = math.radians(base + spread)
        x1 = cx + int(CURSOR_R * 0.45 * math.cos(a))
        y1 = cy + int(CURSOR_R * 0.45 * math.sin(a))
        x2 = cx + int(CURSOR_R * 1.55 * math.cos(a))
        y2 = cy + int(CURSOR_R * 1.55 * math.sin(a))
        pygame.draw.line(surf, color, (x1, y1), (x2, y2), 3)

    pygame.draw.circle(surf, color, (cx, cy), CURSOR_R, 2)
    if pinching:
        pygame.draw.circle(surf, color, (cx, cy), CURSOR_R // 2)


# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud(surf, fonts, f_pop, score, time_left, connected, mock_mode,
             fps, latency_ms, held_obj, pops, t_now):
    f_sm, f_med, f_big = fonts

    # Score
    sc = f_big.render(str(score), True, C_SCORE)
    surf.blit(sc, (W // 2 - sc.get_width() // 2, 10))
    lb = f_med.render("score", True, C_HUD)
    surf.blit(lb, (W // 2 - lb.get_width() // 2, 62))

    # Timer
    secs  = int(time_left)
    t_col = C_TIMER if secs <= 10 else C_HUD
    ts    = f_med.render(f"{secs:02d}s", True, t_col)
    surf.blit(ts, (W - ts.get_width() - 16, 16))

    # Carrying label
    if held_obj is not None:
        col = held_obj.color
        hl  = f_med.render(f"Carrying: {held_obj.label}", True, col)
        surf.blit(hl, (W // 2 - hl.get_width() // 2, 88))

    # Score pops
    for pos, tc, color, text in pops:
        age  = t_now - tc
        frac = max(0.0, 1.0 - age * 1.5)
        yoff = int(age * 65)
        s    = f_pop.render(text, True, tuple(int(c * frac) for c in color))
        surf.blit(s, (int(pos.x) - s.get_width() // 2, int(pos.y) - 24 - yoff))

    # Connection
    if mock_mode:
        dot_col, status = (100, 200, 100), "MOCK"
    elif connected:
        dot_col, status = (100, 200, 100), "GLOVE"
    else:
        dot_col, status = (220, 80, 80), "SEARCHING…"

    pygame.draw.circle(surf, dot_col, (12, 12), 6)
    surf.blit(f_sm.render(status, True, dot_col), (24, 5))
    if not mock_mode:
        surf.blit(f_sm.render(f"FPS {fps:.0f}  lat {latency_ms:.1f}ms", True, C_HUD), (24, 20))

    hint = f_sm.render("Pinch=grab/drop   R=reset cursor   ESC=quit", True, (48, 50, 75))
    surf.blit(hint, (W // 2 - hint.get_width() // 2, H - 14))


def draw_game_over(surf, fonts, score):
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 170))
    surf.blit(overlay, (0, 0))

    f_sm, f_med, _ = fonts
    f_xl = pygame.font.SysFont("consolas", 64)
    t1 = f_xl.render("TIME'S UP", True, C_SCORE)
    t2 = f_med.render(f"Final score: {score}", True, (255, 255, 255))
    t3 = f_sm.render("ENTER — play again    ESC — quit", True, C_HUD)
    surf.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 100))
    surf.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 - 10))
    surf.blit(t3, (W // 2 - t3.get_width() // 2, H // 2 + 60))


# ── Main game loop ────────────────────────────────────────────────────────────
def run_game(reader, mock_mode: bool, calib: dict):
    pygame.init()
    surf  = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Object Grabber — VR Glove")
    clock = pygame.time.Clock()
    pygame.mouse.set_visible(mock_mode)

    fonts = (
        pygame.font.SysFont("consolas", 14),
        pygame.font.SysFont("consolas", 22),
        pygame.font.SysFont("consolas", 48),
    )
    f_obj_lbl = pygame.font.SysFont("consolas", 22, bold=True)
    f_tgt_lbl = pygame.font.SysFont("consolas", 26, bold=True)
    f_tgt_cnt = pygame.font.SysFont("consolas", 14)
    f_pop     = pygame.font.SysFont("consolas", 28, bold=True)

    targets = [TargetZone(i, TARGET_POSITIONS[i]) for i in range(len(TYPES))]

    def new_game():
        return {
            "objects":   [GrabObject(slot_idx=i) for i in range(MAX_OBJECTS)],
            "held_idx":  None,
            "score":     0,
            "last_grab": 0.0,
            "pops":      [],
            "over":      False,
            "game_end":  time.monotonic() + GAME_DURATION,
        }

    g         = new_game()
    cursor    = Vector2(W / 2, H / 2)
    ref_h     = 0.0
    ref_v     = 0.0
    was_pinch = False
    state     = GloveState()

    reader.start()
    running = True

    while running:
        t_now     = time.monotonic()
        time_left = max(0.0, g["game_end"] - t_now)
        clock.tick(FPS_CAP)

        # ── Events ───────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    ref_h, ref_v = finger_direction(state.quat)
                    cursor = Vector2(W / 2, H / 2)
                elif event.key == pygame.K_RETURN and g["over"]:
                    for tgt in targets:
                        tgt.count   = 0
                        tgt.flash_t = -99.0
                    g = new_game()

        # ── Reader ───────────────────────────────────────────────────────────
        if mock_mode:
            reader.update()
        fresh = reader.latest()
        if fresh:
            state = fresh

        flex    = state.flex
        voltage = state.voltage

        vol_lut = ([voltage[0], voltage[1], voltage[2], voltage[2], voltage[3]]
                   if len(voltage) >= 4 else [0.0] * 5)

        norm_flex = [
            normalize_finger(
                flex[i]    if i < len(flex)    else 0.0,
                vol_lut[i] if i < len(vol_lut) else 0.0,
                calib, CHANNEL_TO_FINGER[i])
            for i in range(5)
        ]

        pinching     = norm_flex[CH_INDEX] > PINCH_THRESH_NORM and norm_flex[CH_THUMB] > PINCH_THRESH_NORM
        just_pinch   = pinching and not was_pinch
        just_release = not pinching and was_pinch

        # ── Cursor ───────────────────────────────────────────────────────────
        if mock_mode:
            cursor = Vector2(pygame.mouse.get_pos())
        else:
            h, v = finger_direction(state.quat)
            cursor = Vector2(
                max(0.0, min(float(W), W / 2.0 + (h - ref_h) * IMU_SENS)),
                max(0.0, min(float(H), H / 2.0 + (v - ref_v) * IMU_SENS)),
            )

        # ── Game logic ────────────────────────────────────────────────────────
        if not g["over"] and time_left > 0:
            objects  = g["objects"]
            held_idx = g["held_idx"]

            # Carry object with cursor
            if held_idx is not None:
                objects[held_idx].pos = Vector2(cursor)

            # Grab
            if just_pinch and held_idx is None and (t_now - g["last_grab"]) > GRAB_COOLDOWN:
                best_i, best_d = None, float("inf")
                for i, obj in enumerate(objects):
                    d = (cursor - obj.pos).length()
                    if d < GRAB_DIST and d < best_d:
                        best_d, best_i = d, i
                if best_i is not None:
                    objects[best_i].held = True
                    g["held_idx"]        = best_i
                    g["last_grab"]       = t_now
                    reader.send_haptic(1)

            # Drop
            if just_release and held_idx is not None:
                obj     = objects[held_idx]
                placed  = False

                for tgt in targets:
                    if tgt.cursor_in_range(cursor):
                        if tgt.accepts(obj):
                            tgt.trigger_flash(t_now)
                            g["score"] += 10
                            g["pops"].append((Vector2(cursor), t_now, obj.color, "+10"))
                            reader.send_haptic(47)
                            # Replace with a fresh object at the same slot
                            objects[held_idx] = GrabObject(slot_idx=held_idx)
                        else:
                            obj.snap_to_spawn()
                            g["pops"].append((Vector2(cursor), t_now, (220, 80, 80), "WRONG"))
                            reader.send_haptic(14)
                        placed = True
                        break

                if not placed:
                    obj.snap_to_spawn()

                g["held_idx"] = None

        was_pinch = pinching

        # Expire score pops
        g["pops"] = [(p, tc, c, txt) for p, tc, c, txt in g["pops"] if t_now - tc < 1.0]

        # Game over
        if time_left <= 0 and not g["over"]:
            g["over"] = True
            reader.send_haptic(14)

        # ── Draw ─────────────────────────────────────────────────────────────
        surf.fill(C_BG)

        # Spawn panel
        pygame.draw.rect(surf, C_SPAWN, SPAWN_PANEL, border_radius=14)
        pygame.draw.rect(surf, (38, 42, 72), SPAWN_PANEL, width=2, border_radius=14)
        lbl_panel = fonts[0].render("OBJECTS", True, (55, 60, 100))
        surf.blit(lbl_panel, (SPAWN_PANEL.centerx - lbl_panel.get_width() // 2,
                               SPAWN_PANEL.top + 6))

        # Divider line
        pygame.draw.line(surf, (30, 33, 58), (290, 80), (290, H - 30), 2)

        # Targets
        for tgt in targets:
            tgt.draw(surf, f_tgt_lbl, f_tgt_cnt, t_now)

        # Objects (draw non-held first, held last so it's on top)
        held_idx = g["held_idx"]
        for i, obj in enumerate(g["objects"]):
            if i == held_idx:
                continue
            near = (cursor - obj.pos).length() < GRAB_DIST + 12
            obj.draw(surf, f_obj_lbl, near)
        if held_idx is not None:
            g["objects"][held_idx].draw(surf, f_obj_lbl, False)

        # Cursor
        near_any = (held_idx is None and
                    any((cursor - o.pos).length() < GRAB_DIST + 12 for o in g["objects"]))
        draw_cursor(surf, cursor, pinching, near_any)

        # HUD
        held_obj = g["objects"][held_idx] if held_idx is not None else None
        draw_hud(surf, fonts, f_pop, g["score"], time_left,
                 getattr(reader, "connected", True), mock_mode,
                 getattr(reader, "fps", 60.0), getattr(reader, "latency_ms", 0.0),
                 held_obj, g["pops"], t_now)

        if g["over"]:
            draw_game_over(surf, fonts, g["score"])

        pygame.display.flip()

    reader.stop()
    pygame.quit()


# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    global PINCH_THRESH_NORM
    ap = argparse.ArgumentParser(description="Object Grabber — VR Glove pick-and-place game")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--port", help="Serial port, e.g. COM3")
    grp.add_argument("--mock", action="store_true",
                     help="Mouse position + SPACE/LMB to pinch (no glove needed)")
    ap.add_argument("--baud",   type=int,   default=115200)
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

    if HAS_READER:
        try:
            ports = list_ports()
        except Exception:
            ports = []
        if ports:
            print(f"Auto-selected port: {ports[0]}")
            run_game(SerialReader(ports[0], args.baud), mock_mode=False, calib=calib)
            return

    print("No serial port found — starting in mock mode.")
    print("  Mouse = cursor position,  SPACE / LMB = pinch")
    run_game(MockReader(), mock_mode=True, calib=calib)


if __name__ == "__main__":
    main()
