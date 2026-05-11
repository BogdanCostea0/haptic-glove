#include <Arduino.h>
#include <Wire.h>

#include "Config.h"
#include "GloveState.h"
#include "FlexSensors.h"
#include "IMU.h"
#include "SerialTransport.h"
#include "BLETransport.h"

static FlexSensors  flex;
static IMU          imu;
static SerialTransport serialOut;
static BLETransport    bleOut;

static GloveState state;

// Called when the host sends a command over BLE RX (e.g. "H1\n" = haptic effect 1)
static void onBLECommand(const std::string& cmd) {
    // Future: parse and trigger DRV2605L haptic effect
    Serial.printf("[BLE CMD] %s\n", cmd.c_str());
}

void setup() {
    serialOut.begin(115200);
    serialOut.log("[BOOT] VR Glove starting...");

    Wire.begin(I2C_SDA, I2C_SCL);

    pinMode(BUTTON_PIN, INPUT_PULLUP);

    if (!flex.begin()) {
        serialOut.log("[ERROR] ADS1115 not found — check wiring and I2C address");
        while (true) delay(100);
    }
    serialOut.log("[OK] ADS1115 ready");

    if (!imu.begin()) {
        serialOut.log("[ERROR] MPU-9250/6500 not found — check wiring and I2C address");
        while (true) delay(100);
    }
    serialOut.log("[OK] IMU ready (Mahony filter)");

    bleOut.onCommand(onBLECommand);
    bleOut.begin("VR-Glove");
    serialOut.log("[OK] BLE advertising as 'VR-Glove'");
    serialOut.log("[OK] Setup complete — streaming at 50 Hz");
}

void loop() {
    uint32_t loopStart = millis();

    // ── Read sensors ──────────────────────────────────────────────────────────
    flex.update();
    imu.update();

    // ── Pack state ────────────────────────────────────────────────────────────
    state.flex[0]  = flex.getDegrees(0);  // index
    state.flex[1]  = flex.getDegrees(1);  // middle
    state.flex[2]  = flex.getDegrees(2);  // ring
    state.flex[3]  = flex.getDegrees(3);  // pinky

    state.quat[0]  = imu.getQuatW();
    state.quat[1]  = imu.getQuatX();
    state.quat[2]  = imu.getQuatY();
    state.quat[3]  = imu.getQuatZ();

    state.button    = !digitalRead(BUTTON_PIN);  // active-low
    state.timestamp = millis();

    // ── Transmit ──────────────────────────────────────────────────────────────
    serialOut.send(state);
    bleOut.send(state);

    // ── Rate limiting ─────────────────────────────────────────────────────────
    uint32_t elapsed = millis() - loopStart;
    if (elapsed < LOOP_PERIOD_MS) {
        delay(LOOP_PERIOD_MS - elapsed);
    }
}
