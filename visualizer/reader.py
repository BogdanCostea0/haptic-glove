"""Serial reader thread — parses newline-delimited JSON from the glove firmware."""

import json
import queue
import threading
import time
import serial
import serial.tools.list_ports


def list_ports():
    """Return a list of available COM port names."""
    return [p.device for p in serial.tools.list_ports.comports()]


class GloveState:
    __slots__ = ("flex", "quat", "button", "timestamp")

    def __init__(self):
        self.flex      = [0.0, 0.0, 0.0, 0.0]  # degrees [index, middle, ring, pinky]
        self.quat      = [1.0, 0.0, 0.0, 0.0]  # [w, x, y, z]
        self.button    = False
        self.timestamp = 0


class SerialReader:
    def __init__(self, port: str, baud: int = 115200):
        self._port    = port
        self._baud    = baud
        self._queue   = queue.Queue(maxsize=5)   # hold at most 5 unprocessed frames
        self._running = False
        self._thread  = None

        self.connected  = False
        self.fps        = 0.0
        self.latency_ms = 0.0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def latest(self) -> GloveState | None:
        """Drain the queue and return the newest frame, or None if nothing arrived."""
        frame = None
        while True:
            try:
                frame = self._queue.get_nowait()
            except queue.Empty:
                break
        return frame

    # ── Worker ────────────────────────────────────────────────────────────────

    def _run(self):
        fps_counter = 0
        fps_timer   = time.monotonic()

        while self._running:
            try:
                with serial.Serial(self._port, self._baud, timeout=1.0) as ser:
                    self.connected = True
                    t_prev = None

                    while self._running:
                        raw = ser.readline()
                        if not raw:
                            continue

                        line = raw.decode("utf-8", errors="ignore").strip()

                        # Skip firmware log lines (start with '[')
                        if not line or line.startswith("["):
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        t_now = time.monotonic()
                        if t_prev is not None:
                            self.latency_ms = (t_now - t_prev) * 1000
                        t_prev = t_now

                        state          = GloveState()
                        state.flex     = data.get("f", [0.0] * 4)
                        state.quat     = data.get("q", [1.0, 0.0, 0.0, 0.0])
                        state.button   = bool(data.get("b", 0))
                        state.timestamp = data.get("t", 0)

                        # Drop the oldest frame if the renderer hasn't caught up
                        if self._queue.full():
                            try:
                                self._queue.get_nowait()
                            except queue.Empty:
                                pass
                        self._queue.put_nowait(state)

                        # FPS counter (updated every second)
                        fps_counter += 1
                        elapsed = t_now - fps_timer
                        if elapsed >= 1.0:
                            self.fps    = fps_counter / elapsed
                            fps_counter = 0
                            fps_timer   = t_now

            except serial.SerialException:
                self.connected = False
                if self._running:
                    time.sleep(1.0)   # wait before reconnect attempt
