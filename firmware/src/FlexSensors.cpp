#include "FlexSensors.h"
#include "Config.h"
#include <algorithm>

bool FlexSensors::begin() {
    for (int i = 0; i < 4; i++) {
        _vFlat[i] = FLEX_V_FLAT;
        _vBent[i] = FLEX_V_BENT;
    }
    // ±4.096 V range → 0.125 mV/bit. Flex sensors sit well within this.
    _ads.setGain(GAIN_ONE);
    // 475 SPS: each single-ended read takes ~2 ms → 4 channels = ~8 ms total.
    _ads.setDataRate(RATE_ADS1115_475SPS);
    return _ads.begin(ADS1115_I2C_ADDR);
}

void FlexSensors::update() {
    for (int i = 0; i < 4; i++) {
        int16_t raw  = _ads.readADC_SingleEnded(i);
        _voltage[i]  = _ads.computeVolts(raw);
        _degrees[i]  = mapToDegrees(_voltage[i], _vFlat[i], _vBent[i]);
    }
}

float FlexSensors::getDegrees(uint8_t ch) const { return _degrees[ch]; }
float FlexSensors::getVoltage(uint8_t ch) const { return _voltage[ch]; }

void FlexSensors::setCalibration(uint8_t ch, float vFlat, float vBent) {
    _vFlat[ch] = vFlat;
    _vBent[ch] = vBent;
}

float FlexSensors::mapToDegrees(float v, float vFlat, float vBent) const {
    float deg = (v - vFlat) * (FLEX_DEG_MAX - FLEX_DEG_MIN) / (vBent - vFlat) + FLEX_DEG_MIN;
    return std::max(FLEX_DEG_MIN, std::min(FLEX_DEG_MAX, deg));
}
