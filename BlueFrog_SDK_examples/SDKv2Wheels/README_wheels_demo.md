# Buddy SDK v2 – Wheels Control Demo

This document introduces the Android sample located in `SDKv2Wheels/`. The app showcases how to control Buddy’s differential drive with the Buddy SDK v2 USB API, making it a starting point for anyone who wants to script precise motions, teach navigation concepts, or build classroom activities around robotics and environmental storytelling.

## Goals

- Enable or disable each wheel independently before issuing commands.
- Drive a precise distance at a chosen linear speed.
- Run continuous cruising (forward or backward) until the operator stops it.
- Perform in-place rotations for a given angle or let Buddy spin continuously.
- Trigger an immediate emergency stop on both motors.
- Display live wheel status feedback so you know when actuators are armed, running, or halted.

## Prerequisites

- Buddy robot updated with firmware compatible with Buddy SDK v2.4+ and a registered developer license.
- Android Studio Flamingo (or newer) with Android SDK 30 installed.
- USB connection from Buddy to the development workstation; enable developer mode on the robot.
- Access to the Blue Frog Robotics Maven repository (already referenced via `com.bluefrogrobotics.buddy:BuddySDK:2.4+`).
- Basic familiarity with BuddyActivity lifecycle and permission prompts for USB debugging.

## Project Layout

- `app/src/main/java/com/bfr/sdkv2_wheels/MainActivity.java` – UI wiring and wheel control logic (button listeners, validation, SDK calls).
- `app/src/main/java/com/bfr/sdkv2_wheels/MainApp.java` – Minimal `BuddyApplication` subclass registering the SDK.
- `app/src/main/res/layout/activity_main.xml` – Buttons, input fields, status labels, and enable switches.
- `app/src/main/res/drawable/*.xml` – Styling helpers for the control panel buttons.
- `build.gradle` – Declares the Buddy SDK dependency and compiles against Android 30.

## Usage Flow

1. **Import** the project into Android Studio (`File ▸ Open ▸ SDKv2Wheels`).
2. **Sync Gradle** so the Buddy SDK artifact and Kotlin BOM resolve correctly.
3. **Connect Buddy** over USB, confirm that the debug authorization dialog is accepted on the robot.
4. **Run the app** on Buddy (or an Android device tethered to Buddy’s base if you have the developer kit).
5. **Enable wheels** using the left/right switches. The status labels update every 100 ms via `BuddySDK.Actuators.get*WheelStatus()`.
6. **Send motion commands**:
   - `Move Forward` – requires both speed (m/s) and distance (m) inputs.
   - `Move Non Stop` – takes a single speed value; use `Stop Motors` to halt.
   - `Turn` – needs speed (deg/s) and angle (deg).
   - `Turn Non Stop` – continuous rotation until you stop it.
   - `Stop Motors` – issues `BuddySDK.USB.emergencyStopMotors`.
7. **Observe feedback** – when a command succeeds, a toast shows “Success”; failures surface the SDK error message in Logcat and a toast.

## Tips & Safety

- Always enable both wheels before issuing movement commands; the UI blocks actions if actuators are disabled.
- Start with low speeds (e.g., 0.1 m/s and 20 deg/s) when testing indoors.
- Use the emergency stop button whenever the robot approaches an obstacle; it’s mapped directly to the SDK’s `emergencyStopMotors`.
- Keep Buddy on a flat surface; high angles on ramps may overcurrent the motors.
- Consider wrapping commands in your own safety layer (distance caps, timeout watchdogs) before deploying to classroom sessions.

## Extending the Demo

- Add presets (e.g., “Spin 360°”, “Move 1 m”) to reduce manual input for students.
- Record telemetry via `BuddySDK.Sensors` to teach how wheel speed relates to odometry.
- Combine with your climate-change storytelling module: trigger motions between story chapters to mimic exploration scenes.
- Port the control logic to Kotlin and integrate with MQTT or REST bridges for remote operation.

## Troubleshooting

- **SDK not ready**: Confirm `MainApp` is declared in `AndroidManifest.xml` and USB permissions pop-up was accepted.
- **No movement**: Check that both wheel switches read “Status: STOP”; if they show “DISABLE”, toggle them back on.
- **Gradle sync fails**: Ensure your Maven credentials (if required) are stored in `~/.gradle/gradle.properties`.
- **Buddy drifts**: Recalibrate the robot or reduce speed; mechanical tolerances can cause yaw at higher velocities.

Use this readme as a quick guide for onboarding new teammates or preparing workshop material without exposing proprietary source code.
