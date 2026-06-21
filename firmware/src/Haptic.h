#pragma once
#include <Adafruit_DRV2605.h>

class Haptic {
public:
    bool begin();
    void playEffect(uint8_t effect);   // effect 1–123 (ERM built-in library)
    void stop();

private:
    Adafruit_DRV2605 _drv;
};
