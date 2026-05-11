// ── HandAnimator ──────────────────────────────────────────────────────────────
// Drives 4 finger bone chains from GloveReceiver flex-angle data.
//
// SETUP
//   1. Add this component to the same GameObject as GloveReceiver (or any other).
//   2. Assign the Receiver field in the Inspector.
//   3. Expand "Fingers" (size = 4) and drag in the 3 joint Transforms for each
//      finger: Proximal → Middle → Distal  (index 0 = index finger, … 3 = pinky).
//   4. BendAxis is the LOCAL axis around which each joint rotates when curling.
//      For a typical humanoid rig imported in Unity's default orientation this is
//      Vector3.right (positive X).  Adjust per-finger if needed.
//   5. MaxAngle is the maximum physical bend angle (degrees) at 180° sensor input.
//      ~85° is realistic for a human finger.
// ─────────────────────────────────────────────────────────────────────────────

using UnityEngine;

public class HandAnimator : MonoBehaviour
{
    [System.Serializable]
    public class FingerJoints
    {
        public string    label    = "Finger";
        public Transform proximal;
        public Transform middle;
        public Transform distal;
        [Tooltip("Local rotation axis for curling (usually Vector3.right)")]
        public Vector3   bendAxis  = Vector3.right;
        [Tooltip("Max physical joint angle in degrees at full sensor deflection")]
        [Range(30f, 120f)]
        public float     maxAngle  = 85f;
    }

    [Header("Source")]
    public GloveReceiver receiver;

    [Header("Finger Joints  (0=Index  1=Middle  2=Ring  3=Pinky)")]
    public FingerJoints[] fingers = new FingerJoints[4]
    {
        new FingerJoints { label = "Index"  },
        new FingerJoints { label = "Middle" },
        new FingerJoints { label = "Ring"   },
        new FingerJoints { label = "Pinky"  },
    };

    [Header("Smoothing")]
    [Tooltip("0 = instant, higher = more lag but smoother")]
    [Range(0f, 20f)]
    public float smoothSpeed = 12f;

    // Store smoothed angles per finger
    private float[] _smoothed = new float[4];

    // Joint weight distribution: proximal 50%, middle 35%, distal 15%
    private static readonly float[] Weights = { 0.50f, 0.35f, 0.15f };

    void OnEnable()  => receiver.OnData += HandleData;
    void OnDisable() => receiver.OnData -= HandleData;

    private void HandleData(GloveData data)
    {
        for (int i = 0; i < 4 && i < data.flex.Length; i++)
            _smoothed[i] = data.flex[i];   // raw target updated; smoothing in Update
    }

    void Update()
    {
        for (int i = 0; i < fingers.Length; i++)
        {
            var f = fingers[i];

            // Normalise sensor reading (0–180°) to physical angle (0–maxAngle)
            float t        = Mathf.Clamp01(_smoothed[i] / 180f);
            float target   = t * f.maxAngle;

            // Smooth toward target
            float dt = smoothSpeed > 0f ? smoothSpeed * Time.deltaTime : 1f;
            // (we just use lerp on the angle each frame — simple and stable)

            float[] jointAngles =
            {
                target * Weights[0],
                target * Weights[1],
                target * Weights[2],
            };

            ApplyJoint(f.proximal, f.bendAxis, jointAngles[0], dt);
            ApplyJoint(f.middle,   f.bendAxis, jointAngles[1], dt);
            ApplyJoint(f.distal,   f.bendAxis, jointAngles[2], dt);
        }
    }

    private static void ApplyJoint(Transform joint, Vector3 axis, float angleDeg, float dt)
    {
        if (joint == null) return;
        Quaternion target  = Quaternion.AngleAxis(angleDeg, axis);
        joint.localRotation = Quaternion.Slerp(joint.localRotation, target, dt);
    }
}
