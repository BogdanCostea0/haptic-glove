using UnityEngine;

/// Parsed sensor frame received from the ESP32 glove firmware.
public struct GloveData
{
    public float[]    flex;       // [index, middle, ring, pinky] in degrees
    public Quaternion rotation;   // orientation from IMU Mahony filter
    public bool       button;     // thumb button (true = pressed)
    public uint       timestamp;  // firmware millis()
}
