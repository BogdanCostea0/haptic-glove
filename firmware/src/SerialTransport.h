#pragma once
#include <Arduino.h>
#include "GloveState.h"

class SerialTransport {
public:
    void begin(uint32_t baud = 115200);
    void send(const GloveState& state);
    void log(const char* msg);
};
