// ── GloveOrientation ──────────────────────────────────────────────────────────
// Applies the IMU quaternion from GloveReceiver to a hand root Transform,
// supporting a reference-reset key and a fixed axis-remap offset.
//
// SETUP
//   1. Assign Receiver and Hand Root in the Inspector.
//   2. Enter Play mode, hold your hand in the "neutral" position (palm flat,
//      fingers pointing forward), then press the Reset Key (default: R).
//      The hand model will snap to that orientation as its zero pose.
//   3. If the hand model rotates on the wrong axis, adjust Axis Remap Euler
//      (e.g. try (0,90,0) or (90,0,0)) until motion matches reality.
// ─────────────────────────────────────────────────────────────────────────────

using UnityEngine;

public class GloveOrientation : MonoBehaviour
{
    [Header("Source")]
    public GloveReceiver receiver;

    [Header("Target")]
    [Tooltip("Root transform of the hand model (the whole hand rotates around this)")]
    public Transform handRoot;

    [Header("Orientation")]
    [Tooltip("Key to reset the reference pose (zeros the current IMU orientation)")]
    public KeyCode resetKey = KeyCode.R;

    [Tooltip("Additional fixed rotation applied after the IMU quaternion. " +
             "Use this to correct axis mismatches between the MPU chip and the hand model.")]
    public Vector3 axisRemapEuler = Vector3.zero;

    [Header("Smoothing")]
    [Tooltip("Slerp speed — 0 = instant, higher = snappier")]
    [Range(0f, 30f)]
    public float smoothSpeed = 15f;

    // ── State ─────────────────────────────────────────────────────────────────
    private Quaternion _referenceInv = Quaternion.identity;
    private Quaternion _targetRot    = Quaternion.identity;
    private Quaternion _axisRemap    = Quaternion.identity;

    void Start()
    {
        _axisRemap = Quaternion.Euler(axisRemapEuler);
    }

    void OnEnable()  => receiver.OnData += HandleData;
    void OnDisable() => receiver.OnData -= HandleData;

    private void HandleData(GloveData data)
    {
        // Relative rotation: remove the reference pose, then apply axis remap
        _targetRot = _referenceInv * data.rotation * _axisRemap;
    }

    void Update()
    {
        if (Input.GetKeyDown(resetKey))
            ResetReference();

        if (handRoot == null) return;

        float t = smoothSpeed > 0f
            ? Mathf.Clamp01(smoothSpeed * Time.deltaTime)
            : 1f;

        handRoot.rotation = Quaternion.Slerp(handRoot.rotation, _targetRot, t);
    }

    /// Zero the current IMU reading as the reference (neutral) pose.
    public void ResetReference()
    {
        _referenceInv = Quaternion.Inverse(receiver.LatestData.rotation);
        Debug.Log("[GloveOrientation] Reference reset.");
    }
}
