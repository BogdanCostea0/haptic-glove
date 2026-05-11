#pragma once
#include <stdint.h>

struct GloveState {
    float    flex[4];     // finger bend in degrees: [index, middle, ring, pinky]
    float    quat[4];     // orientation quaternion: [w, x, y, z]
    bool     button;      // thumb button
    uint32_t timestamp;   // millis()
};
