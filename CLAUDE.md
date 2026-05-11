# CLAUDE.md — Haptic Smart Glove

## Project overview

ESP32-based smart glove for VR interaction. Four subsystems, all sharing the same JSON serial protocol:

1. **firmware/** — PlatformIO/Arduino on ESP32 (flex + IMU + haptic at 50 Hz)
2. **visualizer/** — Python/OpenGL 3D diagnostic tool with per-finger calibration
3. **unity/** — Unity C# MonoBehaviours for hand animation and object grabbing
4. **ros2_glove/** — ROS 2 Humble Python driver package

## Hardware

- **ESP32-WROOM-32**: SDA=GPIO21, SCL=GPIO22, Button=GPIO15 (active-low)
- **ADS1115** (0x48): 4-channel 16-bit ADC for flex sensors, 475 SPS
- **MPU-9250/6500** (0x68): 9-DOF IMU, Mahony filter for quaternion output
- **DRV2605L** (0x5A): haptic driver, 123 built-in effects
- **Flex sensors**: 47 kΩ voltage divider, Vout ∈ [1.25 V bent → 2.05 V flat]
- **COM3** = ESP32 (CH340, VID:PID=1A86:7523) on Windows

## Wire protocol

Newline-delimited JSON at 50 Hz over USB serial (115200 baud) and BLE NUS:

```json
{"f":[12.3,45.0,87.1,30.2],"q":[0.9900,0.0100,-0.0200,0.0000],"b":0,"t":12345}
```

- `f` — flex angles in degrees [index, middle, ring, pinky]
- `q` — quaternion **[w, x, y, z]** (firmware order; Unity reorders to x,y,z,w)
- `b` — thumb button (1 = pressed)
- `t` — `millis()` timestamp

Haptic command (host → ESP32): `H<effect_id>\n`

Log lines starting with `[` are debug output — skip them when parsing.

## Build and run commands

### Firmware

```bash
# PlatformIO CLI location on Windows (not on PATH by default)
$env:USERPROFILE\.platformio\penv\Scripts\pio.exe run --target upload
$env:USERPROFILE\.platformio\penv\Scripts\pio.exe device monitor
```

Close the serial monitor before running the visualizer or Unity — only one app can hold COM3 at a time.

### Visualizer

```bash
cd visualizer
pip install -r requirements.txt
python calibrate.py --port COM3      # run once per glove/user
python main.py --port COM3
```

### ROS 2 driver

```bash
cp -r ros2_glove ~/ros2_ws/src/
cd ~/ros2_ws && colcon build --packages-select ros2_glove
source install/setup.bash
ros2 launch ros2_glove glove.launch.py port:=/dev/ttyUSB0
```

## Critical bugs fixed — do not revert

### 1. `firmware/src/IMU.h` — Arduino.h must come first

```cpp
#pragma once
#include <Arduino.h>   // MUST be first — MPU9250.h uses PI, byte, Serial, DEG_TO_RAD
#include <MPU9250.h>
```

If `#include <Arduino.h>` is removed or moved after MPU9250.h, the build fails with
`PI not declared`, `byte not declared`, `Serial not declared`, `DEG_TO_RAD not declared`.

### 2. `firmware/src/BLETransport.cpp` — use string overload for setValue

```cpp
_txChar->setValue(std::string(packet.c_str()));  // correct
// _txChar->setValue(reinterpret_cast<const uint8_t*>(...))  // const mismatch — broken
```

## Known quirks

- VS Code shows red squiggles in firmware files for `Wire.h`, `Arduino.h` — IntelliSense doesn't know the ESP32 SDK paths. PlatformIO builds succeed regardless; ignore the squiggles.
- Quaternion component order: firmware sends `[w,x,y,z]`; Unity `Quaternion` constructor takes `(x,y,z,w)`. GloveReceiver already handles the reorder — don't change it.
- `calibrate.py` must be run with `python calibrate.py --port COM3`, not `.\calibrate.py` (PowerShell will silently fail without the python prefix).
- Unity requires **Api Compatibility Level = .NET Framework** (Player Settings → Other Settings) for `System.IO.Ports` to be available.

## Unity component wiring

All four MonoBehaviours live on the same GameObject (or parent):

| Component | Key fields |
|-----------|-----------|
| GloveReceiver | Port=COM3, BaudRate=115200 |
| GloveOrientation | Receiver ref, HandRoot transform, axisRemapEuler to fix axis mismatch |
| HandAnimator | Receiver ref, 4×3 finger bone transforms, BendAxis=(1,0,0) typical |
| GrabController | Receiver ref, GrabZoneCenter transform, tag filter="Grabbable" |

If the hand rotates on the wrong axis, adjust `axisRemapEuler` on GloveOrientation.
If fingers bend backwards, negate the `BendAxis` on HandAnimator (use `(-1,0,0)`).

## File structure

```
firmware/
  platformio.ini
  src/
    Config.h          pin defs, timing constants
    FlexSensors.h/cpp ADS1115 reading + voltage→angle mapping
    IMU.h/cpp         MPU9250 + Mahony filter
    BLETransport.h/cpp Nordic UART Service (NUS)
    SerialTransport.h/cpp USB serial output
    Protocol.h        inline JSON serializer
    GloveState.h      shared state struct
    main.cpp          50 Hz loop

visualizer/
  reader.py           SerialReader background thread
  hand.py             OpenGL hand model + quaternion→matrix
  main.py             pygame window, 60 FPS render loop
  calibrate.py        per-finger flat/bent calibration
  calibration.json    saved calibration (auto-loaded)
  requirements.txt

unity/Assets/GloveInput/
  GloveData.cs        data struct (flex[], rotation, button, timestamp)
  GloveReceiver.cs    serial thread + ConcurrentQueue + OnData event
  GloveOrientation.cs IMU quaternion → hand root transform
  HandAnimator.cs     flex angles → finger bone rotations
  GrabController.cs   FixedJoint grab + haptic on button

ros2_glove/
  package.xml
  setup.py / setup.cfg
  launch/glove.launch.py
  ros2_glove/glove_driver_node.py   publishes glove/imu, glove/flex, glove/button
                                     subscribes glove/haptic

old/                  legacy RPi Pico prototype — archived, do not modify
paper/                IEEE conference paper (not committed to git yet)
```

## Paper

Located in `paper/paper.md`. Written in Romanian (body) with English title and abstract.
IEEE conference format, 10 sections + 2 appendices (wiring table, 3D print details).
Contains `[PLACEHOLDER]` markers where real experimental measurements are needed.
**Not yet pushed to GitHub** (`paper/` is in `.gitignore`).
