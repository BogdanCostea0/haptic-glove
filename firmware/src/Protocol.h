#pragma once
#include <Arduino.h>
#include "GloveState.h"

// Produces a newline-terminated JSON string for one glove frame.
// Example: {"f":[12.3,45.0,87.1,87.1,30.2],"v":[1.950,1.920,1.900,1.870],"q":[0.9900,0.0100,-0.0200,0.0000],"b":0,"t":12345}\n
// f = flex degrees [index, middle, ring, little, thumb]  (little mirrors ring — no sensor)
// v = raw ADC voltage (V) [index, middle, ring, thumb] — used by calibration tool
inline String serializeState(const GloveState& s) {
    String out;
    out.reserve(180);

    out += F("{\"f\":[");
    for (int i = 0; i < 5; i++) {
        out += String(s.flex[i], 1);
        if (i < 4) out += ',';
    }
    out += F("],\"v\":[");
    for (int i = 0; i < 4; i++) {
        out += String(s.voltage[i], 3);
        if (i < 3) out += ',';
    }
    out += F("],\"q\":[");
    out += String(s.quat[0], 4); out += ',';
    out += String(s.quat[1], 4); out += ',';
    out += String(s.quat[2], 4); out += ',';
    out += String(s.quat[3], 4);
    out += F("],\"b\":");
    out += s.button ? '1' : '0';
    out += F(",\"t\":");
    out += s.timestamp;
    out += '}';

    return out;
}
