import board
import busio
import digitalio
from digitalio import DigitalInOut, Direction, Pull

import time

import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from adafruit_bus_device.i2c_device import I2CDevice

# MPU6500 (or MPU9250) register addresses
MPU6500_ADDR = 0x68
MPU6500_WHO_AM_I = 0x75
MPU6500_ACCEL_XOUT_H = 0x3B
MPU6500_ACCEL_XOUT_L = 0x3C
MPU6500_GYRO_XOUT_H = 0x43
MPU6500_GYRO_XOUT_L = 0x44

# AK8963 (magnetometer) register addresses
AK8963_ADDR = 0x0C
AK8963_HXL = 0x03
AK8963_HXH = 0x04

# Timeout used for serial transmission
TIMEOUT = 0.1

class Glove:
    '''Glove Class for VR Glove. Copyrights Bogdan C.'''

    def __init__(self):
        # DEFINE PINS
        # analog to digital converter
        self.adc_sda = board.GP20
        self.adc_scl = board.GP21
        # HC05 bluetooth module
        self.hc05_tx = board.GP16
        self.hc05_rx = board.GP17
        # button
        self.button_pin = board.GP2
        # gyro
        self.gyro_sda = board.GP18
        self.gyro_scl = board.GP19

        # DEFINE OBJECTS
        # HC-05 module
        self.master_hc05 = busio.UART(self.hc05_tx, self.hc05_rx, baudrate=9600)

        # Button
        self.button = digitalio.DigitalInOut(self.button_pin)
        self.button.switch_to_input(pull=digitalio.Pull.UP)

        # Analog to Digital Converter
        self.i2c_adc = busio.I2C(self.adc_scl, self.adc_sda)
        self.ads = ADS.ADS1115(self.i2c_adc)

        # IMU and Magnetometer
        self.i2c_gyro = busio.I2C(self.gyro_scl, self.gyro_sda)
        self.mpu6500 = I2CDevice(self.i2c_gyro, MPU6500_ADDR)
        self.ak8963 = I2CDevice(self.i2c_gyro, AK8963_ADDR)

        # Flex sensors individual values read
        self.chan0 = AnalogIn(self.ads, ADS.P0)
        self.chan1 = AnalogIn(self.ads, ADS.P1)
        self.chan2 = AnalogIn(self.ads, ADS.P2)
        self.chan3 = AnalogIn(self.ads, ADS.P3)

        # List of mapped input value from flex sensors (unit: degrees)
        self.flex_sensor_degrees_values = [0, 0, 0, 0]
        self.flex_sensor_voltage_values = [0, 0, 0, 0]

        # Button state value
        self.button_input = 0

    def translate(self, value, in_min, in_max, out_min, out_max):
        ''' Map the value from the input range to the output range '''
        return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def update_flex_sensor_values(self):
        ''' This should be called in loop to update real-time data from flex sensors '''
        self.flex_sensor_voltage_values[0] = self.chan0.voltage
        self.flex_sensor_voltage_values[1] = self.chan1.voltage
        self.flex_sensor_voltage_values[2] = self.chan2.voltage
        self.flex_sensor_voltage_values[3] = self.chan3.voltage

        # After updating raw values, update degrees values
        self.transform_voltage_to_degrees()

    def transform_voltage_to_degrees(self):
        ''' Map input value from flex sensorsvoltage to degrees ( 0 to 90 deg) '''
        i = 0
        for voltage in self.flex_sensor_voltage_values:
            self.flex_sensor_degrees_values[i] = self.translate(float(voltage), 2.05, 1.25 , 0, 180)
            i+=1

    def get_button_state(self):
        ''' Get button state: Return True or False '''
        if self.button:
            return True
        return False

    def get_flex_degree_value(self, index):
        ''' Return value of specific flex sensor '''
        return self.flex_sensor_degrees_values[index]

    def get_flex_voltage_value(self, index):
        ''' Return value of specific flex sensor '''
        return self.flex_sensor_degrees_values[index]

    def get_all_flex_voltage_values(self):
        ''' Return value of all flex sensors in voltage '''
        return self.flex_sensor_voltage_values

    def get_all_flex_degrees_values(self):
        ''' Return value of all flex sensors in degrees '''
        return self.flex_sensor_degrees_values

    def read_value_from_register(self, device, reg_addr, length):
        ''' Read bytes from the specified register on the device. '''
        with device:
            result = bytearray(length)
            device.write_then_readinto(bytes([reg_addr]), result)
            return result

    def combine_bytes(self, high, low):
        ''' Combine two bytes to form a signed integer. '''
        value = (high << 8) | low
        if value > 32767:
            value -= 65536
        return value

    def read_mpu6500_accel(self):
        ''' Read acceleration data from mpu6500 (in g's) '''
        accel_data = self.read_value_from_register(self.mpu6500, MPU6500_ACCEL_XOUT_H, 6)
        accel_x = self.combine_bytes(accel_data[0], accel_data[1])
        accel_y = self.combine_bytes(accel_data[2], accel_data[3])
        accel_z = self.combine_bytes(accel_data[4], accel_data[5])
        return accel_x, accel_y, accel_z

    def read_mpu6500_gyro(self):
        ''' Read angular velocity (in degrees per second) '''
        gyro_data = self.read_value_from_register(self.mpu6500, MPU6500_GYRO_XOUT_H, 6)
        gyro_x = self.combine_bytes(gyro_data[0], gyro_data[1])
        gyro_y = self.combine_bytes(gyro_data[2], gyro_data[3])
        gyro_z = self.combine_bytes(gyro_data[4], gyro_data[5])
        return gyro_x, gyro_y, gyro_z

    def read_ak8963_mag(self):
        ''' Read the magnetic field strength (in microteslas) '''
        mag_data = self.read_value_from_register(self.ak8963, AK8963_HXL, 6)
        mag_x = self.combine_bytes(mag_data[1], mag_data[0])
        mag_y = self.combine_bytes(mag_data[3], mag_data[2])
        mag_z = self.combine_bytes(mag_data[5], mag_data[4])
        return mag_x, mag_y, mag_z

    def sendCMD_waitResp(self, cmd, uart=None, timeout=TIMEOUT):
        ''' Send message to serial then wait for response '''
        if uart is None:  # Assign default uart to self.master_hc05
            uart = self.master_hc05
        print("CMD: " + cmd)
        uart.write(cmd)
        self.waitResp(uart, timeout)
        print()

    def waitResp(self, uart= None, timeout= TIMEOUT):
        ''' Wait for response from serial '''
        if uart is None:  # Assign default uart to self.master_hc05
            uart = self.master_hc05
        prvMills = time.monotonic()
        resp = b""
        while (time.monotonic() - prvMills) < timeout:
            if uart.any():
                resp = b"".join([resp, uart.read(1)])
            print(resp)
