#pragma once

// ── I2C ──────────────────────────────────────────────────────────────────────
#define I2C_SDA 21
#define I2C_SCL 22

// ── Button (thumb, active-low with internal pull-up) ─────────────────────────
#define BUTTON_PIN 15

// ── Future: DRV2605L haptic driver shares the same I2C bus (addr 0x5A) ───────
// No extra pin needed when using DRV2605L.
// If you use a bare ERM motor via transistor instead, set this to a PWM pin.
#define HAPTIC_PIN 25

// ── Update rate ───────────────────────────────────────────────────────────────
#define TARGET_HZ       50
#define LOOP_PERIOD_MS  (1000 / TARGET_HZ)

// ── Flex sensor calibration defaults ─────────────────────────────────────────
// Voltage when finger is flat vs. fully bent (per sensor).
// Run the Python calibration tool to measure real values for your glove.
#define FLEX_V_FLAT  2.05f
#define FLEX_V_BENT  1.25f
#define FLEX_DEG_MIN 0.0f
#define FLEX_DEG_MAX 180.0f

// ── ADS1115 ───────────────────────────────────────────────────────────────────
#define ADS1115_I2C_ADDR 0x48   // ADDR pin → GND

// ── MPU-9250 / 6500 ──────────────────────────────────────────────────────────
#define MPU_I2C_ADDR     0x68   // AD0 pin → GND
