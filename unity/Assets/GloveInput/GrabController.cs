// ── GrabController ────────────────────────────────────────────────────────────
// Grabs the nearest Rigidbody tagged "Grabbable" when the thumb button is pressed,
// attaches it via FixedJoint, and releases on button release.
// Sends a haptic command back to the ESP32 on grab/release.
//
// SETUP
//   1. Assign Receiver in the Inspector.
//   2. Assign Grab Zone Center — a Transform at the palm centre (or fingertips).
//   3. On each grabbable object: add a Rigidbody + any Collider, set tag = "Grabbable".
//   4. Optionally enable "Use Haptics" and tune the effect IDs to match
//      your DRV2605L waveform library (effect 1 = strong click, 47 = buzz, etc.)
// ─────────────────────────────────────────────────────────────────────────────

using UnityEngine;

[RequireComponent(typeof(Rigidbody))]
public class GrabController : MonoBehaviour
{
    [Header("Source")]
    public GloveReceiver receiver;

    [Header("Grab zone")]
    [Tooltip("Transform at the palm/finger centre used as the overlap-sphere origin")]
    public Transform grabZoneCenter;
    [Range(0.02f, 0.5f)]
    public float grabRadius = 0.12f;
    public LayerMask grabbableLayer = ~0;   // all layers by default

    [Header("Haptic feedback")]
    public bool useHaptics    = true;
    public int  grabEffectId  = 1;    // DRV2605L waveform: 1 = strong click
    public int  releaseEffectId = 48; // DRV2605L waveform: 48 = short buzz

    // ── State ─────────────────────────────────────────────────────────────────
    private FixedJoint _joint;
    private Rigidbody  _held;
    private bool       _prevButton;

    void OnEnable()  => receiver.OnData += HandleData;
    void OnDisable() => receiver.OnData -= HandleData;

    private void HandleData(GloveData data)
    {
        bool btn = data.button;

        if (btn && !_prevButton) TryGrab();
        else if (!btn && _prevButton) Release();

        _prevButton = btn;
    }

    // ── Grab ──────────────────────────────────────────────────────────────────
    private void TryGrab()
    {
        if (_held != null) return;   // already holding something

        Transform center = grabZoneCenter != null ? grabZoneCenter : transform;
        Collider[] hits  = Physics.OverlapSphere(center.position, grabRadius, grabbableLayer);

        Rigidbody best   = null;
        float     bestDist = float.MaxValue;

        foreach (var col in hits)
        {
            if (!col.CompareTag("Grabbable")) continue;
            var rb = col.attachedRigidbody;
            if (rb == null) continue;
            float d = Vector3.Distance(center.position, col.bounds.center);
            if (d < bestDist) { bestDist = d; best = rb; }
        }

        if (best == null) return;

        _held = best;
        _held.isKinematic = false;

        _joint = gameObject.AddComponent<FixedJoint>();
        _joint.connectedBody   = _held;
        _joint.breakForce      = Mathf.Infinity;
        _joint.breakTorque     = Mathf.Infinity;

        if (useHaptics) receiver.SendHaptic(grabEffectId);
        Debug.Log($"[GrabController] Grabbed: {_held.name}");
    }

    // ── Release ───────────────────────────────────────────────────────────────
    private void Release()
    {
        if (_joint != null) { Destroy(_joint); _joint = null; }
        if (_held  != null)
        {
            // Re-enable physics so the object falls naturally
            _held.isKinematic = false;
            if (useHaptics) receiver.SendHaptic(releaseEffectId);
            Debug.Log($"[GrabController] Released: {_held.name}");
            _held = null;
        }
    }

    // Break event (if a force somehow exceeds the joint limits)
    void OnJointBreak(float _)
    {
        _joint = null;
        _held  = null;
    }

    // ── Debug gizmo ───────────────────────────────────────────────────────────
    void OnDrawGizmosSelected()
    {
        if (grabZoneCenter == null) return;
        Gizmos.color = _held != null ? Color.green : new Color(1f, 1f, 0f, 0.4f);
        Gizmos.DrawWireSphere(grabZoneCenter.position, grabRadius);
    }
}
