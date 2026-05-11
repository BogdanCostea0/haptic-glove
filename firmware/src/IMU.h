#pragma once
#include <Arduino.h>   // must come first — MPU9250.h uses PI, byte, Serial, etc.
#include <MPU9250.h>

class IMU {
public:
    bool begin();
    void update();          // call every loop iteration

    float getQuatW() const;
    float getQuatX() const;
    float getQuatY() const;
    float getQuatZ() const;

private:
    MPU9250 _mpu;
};
