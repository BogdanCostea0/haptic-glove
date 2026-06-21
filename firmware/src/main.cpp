#include <Arduino.h>
#include <Wire.h>

#include "Config.h"
#include "GloveState.h"
#include "FlexSensors.h"
#include "IMU.h"
#include "Haptic.h"
#include "SerialTransport.h"
#include "BLETransport.h"

static FlexSensors  flex;
static IMU          imu;
static Haptic       haptic;
static SerialTransport serialOut;
static BLETransport    bleOut;

static GloveState state;

static void triggerHaptic(const char* cmd) {
    if (cmd[0] == 'H' || cmd[0] == 'h') {
        uint8_t effect = (uint8_t)atoi(cmd + 1);
        if (effect >= 1 && effect <= 123) {
            haptic.playEffect(effect);
            Serial.printf("[HAPTIC] effect %d\n", effect);
        }
    }
}

// Called when the host sends a command over BLE RX (e.g. "H1\n" = haptic effect 1)
static void onBLECommand(const std::string& cmd) {
    triggerHaptic(cmd.c_str());
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

    if (!haptic.begin()) {
        serialOut.log("[WARN] DRV2605L not found — haptic disabled");
    } else {
        serialOut.log("[OK] DRV2605L ready — send H<1-123> to trigger effect");
    }

    bleOut.onCommand(onBLECommand);
    bleOut.begin("VR-Glove");
    serialOut.log("[OK] BLE advertising as 'VR-Glove'");
    serialOut.log("[OK] Setup complete — streaming at 50 Hz");
}

void loop() {
    uint32_t loopStart = millis();

    // ── Handle incoming commands (e.g. H1 from serial monitor) ──────────────
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        triggerHaptic(cmd.c_str());
    }

    // ── Read sensors ──────────────────────────────────────────────────────────
    flex.update();
    imu.update();

    // ── Pack state ────────────────────────────────────────────────────────────
    state.flex[0]    = flex.getDegrees(1);   // index  → A1
    state.flex[1]    = flex.getDegrees(2);   // middle → A2
    state.flex[2]    = flex.getDegrees(3);   // ring   → A3
    state.flex[3]    = state.flex[2];        // little → mirrors ring (no sensor)
    state.flex[4]    = flex.getDegrees(0);   // thumb  → A0

    state.voltage[0] = flex.getVoltage(1);   // index  → A1
    state.voltage[1] = flex.getVoltage(2);   // middle → A2
    state.voltage[2] = flex.getVoltage(3);   // ring   → A3
    state.voltage[3] = flex.getVoltage(0);   // thumb  → A0


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
