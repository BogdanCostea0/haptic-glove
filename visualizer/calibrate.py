#!/usr/bin/env python3
"""Flex sensor calibration tool.

Guides you through capturing flat and bent positions for each finger,
then saves calibration.json.  The visualizer (main.py) loads this file
automatically on startup to normalise the displayed finger angles.

Usage:
    python calibrate.py --port COM3
"""

import sys
import argparse
import json
import time
import statistics
import serial

FINGER_NAMES  = ["index", "middle", "ring", "pinky"]
SAMPLE_COUNT  = 80     # frames averaged per position
DISCARD_EDGES = 10     # drop first N frames (pipeline settling)


# ── Serial helpers ────────────────────────────────────────────────────────────
def _read_frame(ser: serial.Serial) -> dict:
    for _ in range(200):
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line.startswith("{"):
                return json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return {}


def _sample(ser: serial.Serial, channel: int, n: int) -> float:
    """Collect n valid flex readings for channel, return trimmed mean."""
    values = []
    discarded = 0
    print(f"    Sampling", end="", flush=True)
    while len(values) < n:
        frame = _read_frame(ser)
        if "f" not in frame:
            continue
        if discarded < DISCARD_EDGES:
            discarded += 1
            continue
        values.append(frame["f"][channel])
        if len(values) % 10 == 0:
            print(".", end="", flush=True)
    print(f" done ({len(values)} samples)")

    # Trim top/bottom 10% to reject outliers
    values.sort()
    trim = len(values) // 10
    trimmed = values[trim: len(values) - trim]
    return statistics.mean(trimmed)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="VR Glove flex calibration")
    ap.add_argument("--port", required=True, help="Serial port, e.g. COM3")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out",  default="calibration.json",
                    help="Output file (default: calibration.json)")
    args = ap.parse_args()

    print("=" * 50)
    print("  VR Glove — Flex Sensor Calibration")
    print("=" * 50)
    print(f"  Port  : {args.port}")
    print(f"  Output: {args.out}")
    print()
    print("You will be guided through TWO positions for each finger:")
    print("  1. Finger fully FLAT (extended)")
    print("  2. Finger fully BENT (curled into palm)")
    print()
    input("Press Enter to begin...")
    print()

    calib = {}

    with serial.Serial(args.port, args.baud, timeout=2.0) as ser:
        # Flush boot messages
        time.sleep(1.5)
        ser.reset_input_buffer()

        for i, name in enumerate(FINGER_NAMES):
            print(f"── {name.upper()} FINGER ────────────────────────────")

            input(f"  Extend your {name} finger FLAT. Press Enter when ready...")
            flat_val = _sample(ser, i, SAMPLE_COUNT)
            print(f"  Flat captured : {flat_val:.2f}°")
            print()

            input(f"  Curl your {name} finger FULLY BENT. Press Enter when ready...")
            bent_val = _sample(ser, i, SAMPLE_COUNT)
            print(f"  Bent captured : {bent_val:.2f}°")
            print()

            if abs(bent_val - flat_val) < 5.0:
                print(f"  WARNING: flat and bent values are very close ({flat_val:.1f}° vs"
                      f" {bent_val:.1f}°). Check wiring or voltage range.")

            calib[name] = {
                "flat": round(flat_val, 2),
                "bent": round(bent_val, 2),
            }

    # Write output
    with open(args.out, "w") as f:
        json.dump(calib, f, indent=2)

    print("=" * 50)
    print(f"  Saved to {args.out}")
    print("=" * 50)
    print(json.dumps(calib, indent=2))
    print()
    print("Start the visualizer — it will load this file automatically.")


if __name__ == "__main__":
    main()
