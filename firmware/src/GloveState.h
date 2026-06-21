#pragma once
#include <stdint.h>

struct GloveState {
    float    flex[5];     // finger bend in degrees: [index, middle, ring, little, thumb]
    float    voltage[4];  // raw ADC voltage (V): [index, middle, ring, thumb] — no sensor on little
    float    quat[4];     // orientation quaternion: [w, x, y, z]
    bool     button;      // thumb button
    uint32_t timestamp;   // millis()
};
