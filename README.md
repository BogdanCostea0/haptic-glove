# Haptic Smart Glove

ESP32-based smart glove for VR interaction — flex sensing, IMU orientation, haptic feedback, and bidirectional communication over USB serial or BLE.

## Hardware

| Component | Role | I²C Address |
|-----------|------|-------------|
| ESP32-WROOM-32 | Main MCU, BLE, 50 Hz loop | — |
| ADS1115 | 16-bit ADC, 4 flex channels | 0x48 |
| MPU-9250 / 6500 | 9-DOF IMU, Mahony filter | 0x68 |
| DRV2605L | Haptic driver, 123 LRA/ERM effects | 0x5A |
| Flex sensors ×4 | Resistive bend sensors, 47 kΩ divider | — |

I²C bus: SDA = GPIO 21, SCL = GPIO 22. Button: GPIO 15 (active-low).

## Repository structure

```
.
├── firmware/        PlatformIO/Arduino project for the ESP32
├── visualizer/      Python/OpenGL 3D diagnostic visualizer + calibration tool
├── unity/           Unity C# MonoBehaviours for hand animation and grab interaction
├── ros2_glove/      ROS 2 Humble driver package
└── old/             Legacy Raspberry Pi Pico prototype (archived)
```

## Data protocol

All layers share the same newline-delimited JSON format emitted at 50 Hz:

```json
{"f":[12.3,45.0,87.1,30.2],"q":[0.9900,0.0100,-0.0200,0.0000],"b":0,"t":12345}
```

| Field | Type | Description |
|-------|------|-------------|
| `f` | float[4] | Flex angles in degrees — index, middle, ring, pinky |
| `q` | float[4] | Quaternion `[w, x, y, z]` from Mahony filter |
| `b` | int | Thumb button (1 = pressed) |
| `t` | uint | ESP32 `millis()` timestamp |

Haptic command (host → ESP32): `H<effect_id>\n` (e.g. `H1\n` = strong click).

---

## 1. Firmware

**Requirements:** PlatformIO Core or VS Code + PlatformIO extension.

```bash
cd firmware
pio run --target upload      # build and flash to COM3 / /dev/ttyUSB0
pio device monitor           # open serial monitor at 115200 baud
```

Close the serial monitor before running the visualizer or Unity.

---

## 2. Python visualizer

**Requirements:** Python 3.9+, packages in `visualizer/requirements.txt`.

```bash
cd visualizer
pip install -r requirements.txt

# Calibrate first (hold each finger flat, then fully bent when prompted)
python calibrate.py --port COM3       # Windows
python calibrate.py --port /dev/ttyUSB0  # Linux

# Run 3D visualizer
python main.py --port COM3
```

| Key | Action |
|-----|--------|
| R | Reset IMU orientation reference |
| F | Toggle axis overlay |
| ESC | Quit |

Calibration is saved to `calibration.json` and loaded automatically on next run.

---

## 3. Unity integration

**Requirements:** Unity 2021+ with **.NET Framework** API compatibility level
(Edit → Project Settings → Player → Other Settings).

1. Copy `unity/Assets/GloveInput/` into your Unity project's `Assets/` folder.
2. Add **GloveReceiver** to a GameObject — set `Port Name = COM3`, `Baud Rate = 115200`.
3. Add **GloveOrientation** — assign Receiver and the hand root Transform.
4. Add **HandAnimator** — assign Receiver and 12 bone Transforms (4 fingers × proximal/middle/distal).
5. Add **GrabController** (requires a Rigidbody) — assign Receiver and a grab-zone Transform.
6. Tag any grabbable object `Grabbable` and give it a Rigidbody + Collider.
7. Press **R** in Play mode to zero the IMU reference pose.

---

## 4. ROS 2 driver

**Requirements:** ROS 2 Humble, `pyserial` (`pip install pyserial`).

```bash
# Copy into your workspace and build
cp -r ros2_glove ~/ros2_ws/src/
cd ~/ros2_ws
colcon build --packages-select ros2_glove
source install/setup.bash

# Launch
ros2 launch ros2_glove glove.launch.py port:=/dev/ttyUSB0
```

### Published topics

| Topic | Type | Description |
|-------|------|-------------|
| `glove/imu` | `sensor_msgs/Imu` | Mahony-fused orientation at 50 Hz |
| `glove/flex` | `std_msgs/Float32MultiArray` | 4 flex angles in degrees |
| `glove/button` | `std_msgs/Bool` | Thumb button state |

### Subscribed topics

| Topic | Type | Description |
|-------|------|-------------|
| `glove/haptic` | `std_msgs/Int32` | Effect ID forwarded to ESP32 as `H<id>\n` |

### Launch parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `port` | `/dev/ttyUSB0` | Serial port |
| `baud_rate` | `115200` | Baud rate |
| `frame_id` | `glove` | TF frame for IMU messages |
| `reconnect_delay` | `2.0` | Seconds between reconnect attempts |

---

## License

MIT
