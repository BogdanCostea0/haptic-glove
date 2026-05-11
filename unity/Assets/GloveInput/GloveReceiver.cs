// ── GloveReceiver ─────────────────────────────────────────────────────────────
// Reads newline-delimited JSON from the ESP32 over USB serial on a background
// thread, parses each frame into GloveData, and fires OnData on the main thread.
//
// SETUP
//   1. Unity → Edit → Project Settings → Player → Other Settings
//      Api Compatibility Level = ".NET Framework"   (Unity 2019-2021)
//                             or ".NET Standard 2.1" (Unity 2022+)
//   2. Close the PlatformIO serial monitor before entering Play mode —
//      only one application can own a COM port at a time.
//   3. Attach this component to any GameObject, set Port Name in Inspector.
// ─────────────────────────────────────────────────────────────────────────────

using System;
using System.Collections.Concurrent;
using System.IO.Ports;
using System.Threading;
using UnityEngine;

public class GloveReceiver : MonoBehaviour
{
    [Header("Serial")]
    public string portName = "COM3";
    public int    baudRate = 115200;

    [Header("Status (read-only)")]
    [SerializeField] private bool  _connected;
    [SerializeField] private float _fps;
    [SerializeField] private float _latencyMs;

    public bool  IsConnected => _connected;
    public float Fps         => _fps;
    public float LatencyMs   => _latencyMs;

    /// Fired on the Unity main thread once per received frame.
    public event Action<GloveData> OnData;

    public GloveData LatestData { get; private set; }

    // ── Threading ─────────────────────────────────────────────────────────────
    private Thread   _thread;
    private volatile bool _running;
    private SerialPort   _port;

    private readonly ConcurrentQueue<GloveData> _queue = new ConcurrentQueue<GloveData>();

    // FPS tracking (updated by worker thread, read by main thread — close enough)
    private int    _frameCount;
    private double _fpsTimer;

    // ── Unity lifecycle ───────────────────────────────────────────────────────
    void Start()
    {
        _running = true;
        _thread  = new Thread(ReadLoop) { IsBackground = true, Name = "GloveSerial" };
        _thread.Start();
    }

    void Update()
    {
        // Drain queue — fire event on main thread (Unity API is not thread-safe)
        while (_queue.TryDequeue(out GloveData d))
        {
            LatestData = d;
            OnData?.Invoke(d);
        }
    }

    void OnDestroy()
    {
        _running = false;
        try { _port?.Close(); } catch { }
        _thread?.Join(2000);
    }

    // ── Worker thread ─────────────────────────────────────────────────────────
    private void ReadLoop()
    {
        while (_running)
        {
            try
            {
                _port = new SerialPort(portName, baudRate) { ReadTimeout = 2000 };
                _port.Open();
                _connected = true;

                double prevTime = ElapsedSeconds();

                while (_running)
                {
                    string line;
                    try   { line = _port.ReadLine().Trim(); }
                    catch (TimeoutException) { continue; }

                    if (string.IsNullOrEmpty(line) || line[0] == '[') continue;

                    Packet pkt = JsonUtility.FromJson<Packet>(line);
                    if (pkt == null || pkt.f == null || pkt.f.Length < 4 ||
                        pkt.q == null || pkt.q.Length < 4) continue;

                    // q from firmware: [w, x, y, z]
                    // Unity Quaternion ctor: (x, y, z, w)
                    var data = new GloveData
                    {
                        flex      = pkt.f,
                        rotation  = new Quaternion(pkt.q[1], pkt.q[2], pkt.q[3], pkt.q[0]),
                        button    = pkt.b != 0,
                        timestamp = pkt.t,
                    };

                    // Keep only the latest 3 frames if the main thread is slow
                    while (_queue.Count >= 3) _queue.TryDequeue(out _);
                    _queue.Enqueue(data);

                    // FPS / latency
                    double now = ElapsedSeconds();
                    _latencyMs = (float)((now - prevTime) * 1000.0);
                    prevTime   = now;
                    _frameCount++;
                }

                _port.Close();
            }
            catch (Exception e)
            {
                _connected = false;
                Debug.LogWarning($"[GloveReceiver] {e.Message}");
                try { _port?.Close(); } catch { }
                _port = null;
                if (_running) Thread.Sleep(1000);
            }
        }
        _connected = false;
    }

    // ── Haptic command ────────────────────────────────────────────────────────
    /// Send a haptic effect ID to the ESP32 (e.g. 1 = click, 2 = buzz).
    /// The firmware's BLE RX / serial RX handler receives "H<id>\n".
    public void SendHaptic(int effectId)
    {
        if (_port == null || !_port.IsOpen) return;
        try { _port.Write($"H{effectId}\n"); }
        catch (Exception e) { Debug.LogWarning($"[GloveReceiver] haptic send failed: {e.Message}"); }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    private static double ElapsedSeconds() =>
        (double)System.Diagnostics.Stopwatch.GetTimestamp() /
        System.Diagnostics.Stopwatch.Frequency;

    // Must match the JSON keys sent by Protocol.h
    [Serializable]
    private class Packet
    {
        public float[] f;   // flex degrees
        public float[] q;   // quaternion [w, x, y, z]
        public int     b;   // button
        public uint    t;   // timestamp
    }
}
