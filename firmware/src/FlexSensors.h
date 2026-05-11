#pragma once
#include <Adafruit_ADS1X15.h>

class FlexSensors {
public:
    bool  begin();
    void  update();

    float getDegrees(uint8_t ch) const;
    float getVoltage(uint8_t ch) const;

    // Override per-sensor voltage range (run calibration tool to get real values)
    void setCalibration(uint8_t ch, float vFlat, float vBent);

private:
    Adafruit_ADS1115 _ads;
    float _voltage[4] = {};
    float _degrees[4] = {};
    float _vFlat[4]   = {};
    float _vBent[4]   = {};

    float mapToDegrees(float v, float vFlat, float vBent) const;
};
