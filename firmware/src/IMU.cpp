#include "IMU.h"
#include "Config.h"

bool IMU::begin() {
    bool ok = _mpu.setup(MPU_I2C_ADDR);
    if (!ok) return false;

    // Mahony is lighter than Madgwick and equally stable for this use-case.
    _mpu.selectFilter(QuatFilterSel::MAHONY);
    return true;
}

void IMU::update() {
    _mpu.update();
}

float IMU::getQuatW() const { return _mpu.getQuaternionW(); }
float IMU::getQuatX() const { return _mpu.getQuaternionX(); }
float IMU::getQuatY() const { return _mpu.getQuaternionY(); }
float IMU::getQuatZ() const { return _mpu.getQuaternionZ(); }
