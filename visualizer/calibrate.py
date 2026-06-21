#!/usr/bin/env python3
"""Flex sensor calibration tool.

Guides you through capturing the flat (extended) and bent (curled) positions
for each finger.  Reads raw ADC voltage from the "v" field in the JSON stream
and saves per-finger min/max voltage intervals to calibration.json.

All Python tools (visualizer, pinch game) use these intervals to map raw
voltage → 0–100 % bend, independent of the firmware's hard-coded defaults.

Usage:
    python calibrate.py --port COM3
"""

import argparse
import json
import time
import statistics
import serial

# Physical finger per ADS1115 channel — must match CHANNEL_TO_FINGER in pinch_game.py
FINGER_NAMES  = ["index", "middle", "ring", "thumb"]   # f[0]=index f[1]=middle f[2]=ring f[3]=thumb
SAMPLE_COUNT  = 80     # frames averaged per position
DISCARD_EDGES = 10     # drop first N frames (ADC pipeline settling)


# Channel → finger name as the firmware sends it (v[0]=index, v[1]=middle, v[2]=ring, v[3]=thumb)
CHANNEL_LABELS = ["index(A1)", "middle(A2)", "ring(A3)", "thumb(A0)"]

# ── Serial helpers ────────────────────────────────────────────────────────────

def _read_frame(ser: serial.Serial) -> dict:
    for _ in range(400):
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line.startswith("{"):
                return json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return {}


def live_monitor(ser: serial.Serial, seconds: int = 10):
    """Print a live table of all 4 voltages for `seconds` seconds.

    Lets you verify which ADC channel responds to which finger before
    starting the calibration.  Press Ctrl-C to skip early.
    """
    print()
    print(f"  Live voltage monitor ({seconds}s) — bend each finger and watch which column moves:")
    print(f"  {'v[0] index(A1)':>18}  {'v[1] middle(A2)':>18}  {'v[2] ring(A3)':>18}  {'v[3] thumb(A0)':>18}")
    print(f"  {'-'*18}  {'-'*18}  {'-'*18}  {'-'*18}")

    import time
    t_end = time.monotonic() + seconds
    try:
        while time.monotonic() < t_end:
            frame = _read_frame(ser)
            v = frame.get("v", [])
            if len(v) < 4:
                continue
            row = "  " + "  ".join(f"{v[i]:>17.4f}V" for i in range(4))
            print(row, end="\r", flush=True)
    except KeyboardInterrupt:
        pass
    print()
    print()


def _sample_voltage(ser: serial.Serial, channel: int, n: int) -> float:
    """Collect n valid voltage readings for channel and return trimmed mean.

    Falls back to degree-based sampling if the firmware doesn't include
    the 'v' field (older firmware without voltage output).
    """
    ser.reset_input_buffer()   # discard frames queued during input() pause
    values = []
    use_voltage = None   # determined on first valid frame
    discarded = 0

    print(f"    Sampling", end="", flush=True)
    while len(values) < n:
        frame = _read_frame(ser)
        if not frame:
            print("\n    WARNING: no valid frame received — check port/baud.", flush=True)
            continue

        if use_voltage is None:
            use_voltage = "v" in frame
            if not use_voltage:
                print("\n    NOTE: 'v' field not found in firmware output — "
                      "falling back to degree values ('f').\n"
                      "    For best results flash updated firmware.", flush=True)

        if use_voltage:
            if "v" not in frame or len(frame["v"]) <= channel:
                continue
            val = frame["v"][channel]
        else:
            if "f" not in frame or len(frame["f"]) <= channel:
                continue
            val = frame["f"][channel]

        if discarded < DISCARD_EDGES:
            discarded += 1
            continue

        values.append(val)
        if len(values) % 10 == 0:
            print(".", end="", flush=True)

    print(f" done ({len(values)} samples, {'voltage' if use_voltage else 'degrees'})")

    values.sort()
    trim = max(1, len(values) // 10)
    return statistics.mean(values[trim: len(values) - trim])


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="VR Glove flex calibration")
    ap.add_argument("--port", required=True, help="Serial port, e.g. COM3")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out",  default="calibration.json",
                    help="Output file (default: calibration.json)")
    args = ap.parse_args()

    print("=" * 52)
    print("  VR Glove — Flex Sensor Calibration")
    print("=" * 52)
    print(f"  Port  : {args.port}")
    print(f"  Output: {args.out}")
    print()
    print("Captures the VOLTAGE interval [flat_v, bent_v] for each finger.")
    print("These per-finger min/max values are used by the visualizer and")
    print("the pinch game to normalise flex readings correctly.")
    print()
    print("You will go through TWO positions for each finger:")
    print("  1. Finger fully FLAT (extended)")
    print("  2. Finger fully BENT (curled into palm)")
    print()
    input("Press Enter to begin...")
    print()

    calib = {}

    with serial.Serial(args.port, args.baud, timeout=2.0) as ser:
        time.sleep(1.5)
        ser.reset_input_buffer()

        live_monitor(ser, seconds=15)
        input("Sensors look right? Press Enter to start calibration, or Ctrl-C to abort.")
        print()

        for i, name in enumerate(FINGER_NAMES):
            print(f"── {name.upper()} ───────────────────────────────────────")

            input(f"  Extend your {name} finger FLAT. Press Enter when ready...")
            flat_val = _sample_voltage(ser, i, SAMPLE_COUNT)
            print(f"  Flat captured : {flat_val:.4f}")
            print()

            input(f"  Curl your {name} finger FULLY BENT. Press Enter when ready...")
            bent_val = _sample_voltage(ser, i, SAMPLE_COUNT)
            print(f"  Bent captured : {bent_val:.4f}")
            print()

            span = abs(bent_val - flat_val)
            if span < 0.02:
                print(f"  WARNING: flat and bent values are very close "
                      f"({flat_val:.4f} vs {bent_val:.4f}, span={span:.4f}).")
                print(f"  Check sensor wiring for channel {i} ({name}).")
            else:
                print(f"  OK — span {span:.4f}  ({span/flat_val*100:.1f}% of flat value)")

            calib[name] = {
                "flat_v": round(flat_val, 4),
                "bent_v": round(bent_val, 4),
            }
            print()

    with open(args.out, "w") as f:
        json.dump(calib, f, indent=2)

    print("=" * 52)
    print(f"  Saved to {args.out}")
    print("=" * 52)
    print(json.dumps(calib, indent=2))
    print()
    print("Start the visualizer or pinch game — calibration is loaded automatically.")


if __name__ == "__main__":
    main()
