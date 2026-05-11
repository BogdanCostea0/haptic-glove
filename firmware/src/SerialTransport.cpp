#include "SerialTransport.h"
#include "Protocol.h"

void SerialTransport::begin(uint32_t baud) {
    Serial.begin(baud);
    while (!Serial) delay(10);  // wait for USB-CDC on native USB boards
}

void SerialTransport::send(const GloveState& state) {
    Serial.println(serializeState(state));
}

void SerialTransport::log(const char* msg) {
    Serial.println(msg);
}
