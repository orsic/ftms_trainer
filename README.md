# trainer

Ride Zwift `.zwo` workouts on an FTMS smart trainer (Van Rysel D100) from a Linux laptop. The program:

- runs the trainer in ERG mode, so it holds each workout target;
- records two power sources (the D100 and a 4iiii crank power meter), heart rate from a Garmin watch, and cadence;
- writes a FIT file for Strava and Garmin Connect, plus a CSV with every raw sample;
- uses the right half of a Zwift Click v2 to control YouTube in Chrome and to change FTP mid-ride.

Only the trainer is required. If the power meter, heart rate or Click is missing or drops out, the ride continues and the missing values are left empty.

## Setup

Everything runs in podman, and the source is bind-mounted rather than copied into the image.

1. Copy the settings file: `cp vars.env.example vars.env`. Then set `FTP` and `OUTPUT_DIR`.
2. Wake up the devices:
   - Turn on the trainer.
   - Spin the cranks so the 4iiii wakes up.
   - On the Fenix 7, enable *Broadcast Heart Rate*: hold MENU, then Sensors & Accessories, then Wrist Heart Rate, then Broadcast Heart Rate.
   - Press a button on the right Click.
3. Run `./run.sh scan` and copy the addresses into `vars.env`. Each device's role is labelled in the scan output:

   | Variable | Device |
   |---|---|
   | `TRAINER_ADDR` | FTMS trainer (D100) |
   | `POWER_METER_ADDR` | cycling power (4iiii) |
   | `HEART_RATE_ADDR` | heart rate (Fenix) |
   | `CLICK_ADDR` | Zwift controller (right Click) |

   The D100 also advertises cycling power, so pick the 4iiii by its name.
4. Run `./run.sh click-learn` and press every button on the right Click. The command prints the bit position for each press. If the positions differ from `BUTTON_BITS` in `trainer/click.py`, update that dict.

`run.sh` mounts:
- the system D-Bus socket, for BlueZ;
- the session D-Bus socket, for Chrome's media controls through `playerctl`;
- the PulseAudio/PipeWire socket, for volume through `pactl`.

## Commands

| Command | What it does |
|---|---|
| `./run.sh scan [--seconds N]` | Lists nearby BLE devices and what each one is. |
| `./run.sh click-learn` | Prints Click button bits and actions as you press. |
| `./run.sh ride workouts/FILE.zwo` | Rides a workout. The `.zwo` file must be inside this repo, for example in `workouts/`. |
| `./run.sh ride workouts/FILE.zwo --demo [--speed N]` | Same screen with simulated devices; no Bluetooth needed. See [Demo mode](#demo-mode). |
| `./run.sh export OUTPUT_DIR/FILE.csv` | Rebuilds the `.fit` from a ride's CSV, for example after a crash. |
| `./run.sh test [pytest args]` | Runs the tests, for example `./run.sh test tests/test_zwo.py`. |

## Workouts (ZWO input)

Workouts are Zwift `.zwo` files: plain XML. Put them in `workouts/` inside this repo. Only the repo directory is mounted into the container, so files elsewhere are not visible.

Where to get them:
- **Zwift's own folder.** Zwift keeps custom workouts in `Documents/Zwift/Workouts/<user id>/`.
- **Free libraries.** Sites such as whatsonzwift.com offer workouts to download.
- **Write your own.** Use an editor such as ZWOFactory, or edit the XML by hand.

`workouts/short-test.zwo` is a 2-minute example.

```xml
<workout_file>
    <name>Sweet Spot 3x10</name>          <!-- shown in the dashboard header and output file names -->
    <workout>
        <Warmup Duration="600" PowerLow="0.50" PowerHigh="0.75"/>
        <IntervalsT Repeat="3" OnDuration="600" OffDuration="300" OnPower="0.90" OffPower="0.55"/>
        <Cooldown Duration="300" PowerLow="0.70" PowerHigh="0.40"/>
    </workout>
</workout_file>
```

**Units:**
- `Duration` values are seconds. Decimals such as `"300.0"` are accepted and truncated to whole seconds.
- Power values are fractions of FTP: `0.90` means 90% of FTP. Absolute watts are not supported.
- The target is `round(fraction × FTP)`, recalculated every second. Changing FTP during the ride shifts every target.

| Element | Attributes used | Behaviour |
|---|---|---|
| `SteadyState` | `Duration`, `Power` (or `PowerLow`) | Constant ERG target. |
| `Warmup`, `Ramp` | `Duration`, `PowerLow`, `PowerHigh` | Linear ramp from `PowerLow` to `PowerHigh`. |
| `Cooldown` | `Duration`, `PowerLow`, `PowerHigh` | Linear ramp that always goes down, from the higher value to the lower. ZWO files disagree on the attribute order for cooldowns. |
| `IntervalsT` | `Repeat`, `OnDuration`, `OffDuration`, `OnPower`, `OffPower` | Expanded into `Repeat` on/off pairs. Each one is a separate segment and FIT lap. |
| `FreeRide`, `MaxEffort` | `Duration` | No ERG target. The trainer switches to flat simulation (0% grade), and you ride by feel. |

**Not used:**
- **Ignored parts:** other elements, `<textevent>` messages, cadence targets (`Cadence`, `CadenceLow`/`CadenceHigh`) and the `<author>`, `<description>`, `<sportType>` and `<tags>` fields.
- **Missing `<workout>` element:** the ride doesn't start and shows an error.
- **Missing `<name>`:** the header shows "Workout".

## Riding

- **Start.** The dashboard appears while the devices connect. The workout clock starts at your first pedal stroke.
- **Targets.** Each target is `FTP × segment %`, and ramps change smoothly. FreeRide and MaxEffort segments use flat simulation mode instead of ERG.
- **End.** After the last segment the trainer switches to free ride and keeps recording.
- **Controls on screen.** The two bottom lines of the dashboard always show the Click buttons (generated from the mapping in `trainer/click.py`) and the keyboard keys.
- **Keyboard.** The keys work in every ride, as a backup for the Click:

  | Key | Action |
  |---|---|
  | `+` / `-` | FTP up / down |
  | space | play/pause |
  | `n` / `p` | next / previous video |
  | `]` / `[` | volume up / down |
  | `q` | finish |

- **Finishing.** Press `q` or Ctrl+C to finish. The program then writes the files and prints a summary: average and normalized power for both power sources, and average heart rate.
- **Trainer drops out.** The program reconnects and sends the current target again.
- **Trainer missing at start.** If the D100 hasn't connected within 45 s, or doesn't support ERG, the ride stops with an error.
- **Log file.** Everything is logged to `OUTPUT_DIR/trainer.log`.

### Demo mode

`--demo` replaces every device with a simulation, so you can try the screen and controls without the hardware:

- **Simulated trainer:** it holds the target with a few watts of noise, and rides at 150 W in free-ride segments.
- **Simulated power meter:** the 4iiii reads about 3% below the trainer, with a balance near 49/51.
- **Simulated heart rate:** it drifts toward the effort level.
- **Speed:** `--speed N` runs the workout N times faster. For example, `--speed 20` plays the 2-minute `short-test.zwo` in 6 seconds.
- **Controls:** use the keyboard keys listed under [Riding](#riding) in place of the Click. The media keys really control Chrome and the system volume.
- **Output:** files are written as usual, with a `_demo` suffix.

### Zwift Click v2 (right controller)

| Button | Short press | Long press (≥ 0.6 s) |
|---|---|---|
| A | play/pause | — |
| Y | volume up | — |
| B | volume down | — |
| Z | next video | previous video |
| + | FTP +5 W | FTP −5 W |

- **FTP changes.** They shift every target right away. They last for this ride only; the next ride starts from `FTP` in `vars.env`.
- **Media control.** It works with Chrome or Chromium, through the browser's media session. Volume changes the system default output.
- **Left controller.** It isn't used. It needs a Zwift unlock about every 24 hours.
- **Keepalive.** The right controller is sent a keepalive every 3 s so it doesn't go to sleep.

## Output

Each ride writes `OUTPUT_DIR/YYYY-MM-DD_HHMM_<workout>.csv` and a matching `.fit`.

- **CSV:** one row per second. Columns:
  - `timestamp`, `elapsed`, `segment`, `ftp`, `target_power`
  - `trainer_power`, `trainer_cadence`, `speed`
  - `pm_power`, `pm_cadence`, `pm_balance_left`
  - `heart_rate`

  Missing values are left empty. Rows are flushed as they're written, so a crash loses at most one second.
- **FIT:** an indoor cycling activity.
  - Standard fields: power (from the D100), heart rate, cadence (from the D100, or the 4iiii if the D100 has none), speed and distance.
  - Developer fields: `pm_power`, `pm_cadence`, `pm_balance_left` and `target_power`.
  - There is one lap per workout segment.
  - To use it, upload the `.fit` to Strava or Garmin Connect.

## Development

`Session` depends only on the device interface in `trainer/devices.py`, never on concrete devices. That interface has:

- `SensorLike` and `TrainerLike` protocols;
- a `Devices` bundle with the trainer, power meter, HR and Click, plus the clocks and the tick interval;
- a `DeviceStrategy` protocol with one method, `build(on_action) -> Devices`.

There are two strategies:

| Strategy | Where | Used by |
|---|---|---|
| `BleDevices` | `trainer/devices.py` | normal rides; real Bluetooth devices, addressed from `vars.env` |
| `DemoDevices` | `trainer/demo.py` | `--demo`; simulated devices with a sped-up clock |

`ride()` chooses the strategy, and `Session` calls `build(self.on_action)` so that Click presses reach it. To support different hardware, write a new strategy. The session and dashboard stay unchanged.
