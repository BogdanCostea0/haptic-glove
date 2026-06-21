#include "Haptic.h"

bool Haptic::begin() {
    if (!_drv.begin()) return false;
    _drv.selectLibrary(1);              // ERM motors (library 1)
    _drv.setMode(DRV2605_MODE_INTTRIG); // fire on go()
    return true;
}

void Haptic::playEffect(uint8_t effect) {
    _drv.setWaveform(0, effect);
    _drv.setWaveform(1, 0);  // end of sequence
    _drv.go();
}

void Haptic::stop() {
    _drv.stop();
}
