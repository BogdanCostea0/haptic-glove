''' VR Glove main code '''

import time
from glove import Glove

glove = Glove()

while True:
    glove.update_flex_sensor_values()

    print(f'Voltage values: {glove.get_all_flex_voltage_values()}')
    print(f'Degrees values: {glove.get_all_flex_degrees_values()}')

    accel_x, accel_y, accel_z = glove.read_mpu6500_accel()
    gyro_x, gyro_y, gyro_z = glove.read_mpu6500_gyro()
    mag_x, mag_y, mag_z = glove.read_ak8963_mag()

    print("Accel: X={0}, Y={1}, Z={2}".format(accel_x, accel_y, accel_z))
    print("Gyro: X={0}, Y={1}, Z={2}".format(gyro_x, gyro_y, gyro_z))
    print("Mag: X={0}, Y={1}, Z={2}".format(mag_x, mag_y, mag_z))
    print("-----")

    time.sleep(0.5)