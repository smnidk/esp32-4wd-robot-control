# ESP32 4WD Robot Control Station

Desktop control app and firmware extensions for an ESP32 4WD car, with
obstacle detection and a simplified 2D map of the surroundings.
Diploma project, Astana Polytechnic, 2026.

> **Based on** the [Freenove 4WD Car Kit for ESP32](https://github.com/Freenove/Freenove_4WD_Car_Kit_for_ESP32)
> (hardware, base firmware and base client). Released under
> CC BY-NC-SA 3.0, same as the original. Freenove name and logo are
> trademarks of Freenove Creative Technology Co., Ltd.

## What I added

- **Safety stop** (`06_3_Multi_Functional_Car.ino`): the car stops forward
  motion when an obstacle is closer than 15 cm; checked every 60 ms and
  before each motor command.
- **Distance filtering**: 5 ultrasonic readings per measurement, invalid
  values discarded, minimum taken.
- **Telemetry**: distance sent to the desktop app over TCP every 300 ms.
- **2D map widget** (`main.py`, `RadarMapWidget`): converts distance and
  sensor angle to coordinates, estimates robot position from motion
  commands (no encoders, so the map drifts), removes duplicate points,
  thread-safe drawing with PyQt5.
- Dark UI theme, battery level indicator.

## What comes from the kit

Motor, LED, servo and camera libraries (`Freenove_4WD_Car_*`),
`Command.py`, `Client_Ui.py`, `Video.py`.

## Run

1. Open the `.ino` in Arduino IDE, set your Wi-Fi in `WiFi_Init()`.
2. `pip install PyQt5 opencv-python numpy`
3. `python main.py`, enter the robot's IP, press Connect.

## Limitations

Position is estimated from commanded speed, not measured; the map is
approximate. Distance measurement blocks the main loop for up to ~100 ms.
