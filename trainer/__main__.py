"""CLI: scan | click-learn | ride FILE.zwo | export FILE.csv"""

import argparse
import asyncio
import curses
import logging
import os
import re
import signal
import sys
from datetime import datetime
from pathlib import Path

from bleak import BleakScanner

from trainer.click import BUTTON_BITS, Click
from trainer.demo import DemoDevices
from trainer.devices import BleDevices
from trainer.fit_export import export_fit
from trainer.recorder import Recorder, read_rows, summarize
from trainer.session import Session, run_session
from trainer.tui import KEYS, draw, init_screen
from trainer.zwo import parse_zwo

SERVICE_LABELS = {
    "00001826-0000-1000-8000-00805f9b34fb": "FTMS trainer -> TRAINER_ADDR",
    "00001818-0000-1000-8000-00805f9b34fb": "cycling power -> POWER_METER_ADDR",
    "0000180d-0000-1000-8000-00805f9b34fb": "heart rate -> HEART_RATE_ADDR",
    "0000fc82-0000-1000-8000-00805f9b34fb": "Zwift controller -> CLICK_ADDR",
    "00000001-19ca-4651-86e5-fa29dcdd09d1": "Zwift controller -> CLICK_ADDR",
}


async def scan(seconds: float) -> None:
    print(f"Scanning for {seconds:.0f} s ...")
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    for address, (device, adv) in sorted(found.items(), key=lambda kv: -kv[1][1].rssi):
        labels = [label for uuid, label in SERVICE_LABELS.items() if uuid in adv.service_uuids]
        name = adv.local_name or device.name or "?"
        print(f"{address}  {adv.rssi:4d} dBm  {name:24.24s}  {', '.join(labels)}")


async def click_learn(address: str) -> None:
    names = {bit: name for name, bit in BUTTON_BITS.items()}
    last = [-1]

    def on_mask(pressed: int) -> None:
        if pressed != last[0]:
            last[0] = pressed
            bits = [b for b in range(32) if pressed >> b & 1]
            print(
                f"pressed bits: {bits or '-'}  ({', '.join(names.get(b, '?') for b in bits) or 'released'})"
            )

    click = Click(address, on_action=lambda a: print(f"  -> action: {a}"), on_mask=on_mask)
    print("Press each button; Ctrl+C to quit.")
    await click.run()


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()


async def _ride(scr: "curses.window", session: Session) -> None:
    init_screen(scr)
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop.set)

    def show(snap) -> None:
        key = draw(scr, snap)
        if key in (ord("q"), ord("Q")):
            stop.set()
        elif 0 <= key < 256 and chr(key) in KEYS:
            session.on_action(KEYS[chr(key)])

    await run_session(session, stop, show)


def ride(zwo: Path, out_dir: Path, demo: bool = False, speed: float = 1.0) -> None:
    strategy = DemoDevices(speed) if demo else BleDevices.from_env()
    workout = parse_zwo(zwo)
    stem = out_dir / f"{datetime.now():%Y-%m-%d_%H%M}_{_slug(workout.name)}{'_demo' if demo else ''}"
    csv_path, fit_path = stem.with_suffix(".csv"), stem.with_suffix(".fit")
    try:
        with Recorder(csv_path) as recorder:
            session = Session(workout, int(os.environ["FTP"]), strategy, recorder)
            curses.wrapper(lambda scr: asyncio.run(_ride(scr, session)))
    finally:
        rows = read_rows(csv_path)
        if rows:
            export_fit(csv_path, fit_path)
            print_summary(rows, csv_path, fit_path)
        else:
            print("No samples recorded (never started pedaling).")
            csv_path.unlink()


def print_summary(rows: list, csv_path: Path, fit_path: Path) -> None:
    s = summarize(rows)
    print(f"Duration       {s['duration'] // 60}:{s['duration'] % 60:02d}")
    for key, label in (("trainer_power", "D100"), ("pm_power", "4iiii")):
        if s[key] is None:
            print(f"{label:<14} --")
        else:
            avg, np_ = s[key]
            print(f"{label:<14} avg {avg:.0f} W   NP {'--' if np_ is None else f'{np_:.0f}'} W")
    hr = s["heart_rate"]
    print(f"Heart rate     {'--' if hr is None else f'avg {hr:.0f} bpm'}")
    host_dir = Path(os.environ.get("HOST_OUTPUT_DIR", csv_path.parent))  # paths as seen outside the container
    print(f"CSV            {host_dir / csv_path.name}")
    print(f"FIT            {host_dir / fit_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="trainer")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="list nearby BLE devices and what they are")
    p.add_argument("--seconds", type=float, default=10)
    sub.add_parser("click-learn", help="print Zwift Click button bits as you press them")
    p = sub.add_parser("ride", help="ride a .zwo workout")
    p.add_argument("zwo", type=Path)
    p.add_argument("--demo", action="store_true", help="simulated devices, no Bluetooth needed")
    p.add_argument("--speed", type=float, default=1.0, help="with --demo: run time N times faster")
    p = sub.add_parser("export", help="(re)build a .fit file from a ride .csv")
    p.add_argument("csv", type=Path)
    args = parser.parse_args()

    out_dir = Path(os.environ.get("OUTPUT_DIR", "."))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        filename=out_dir / "trainer.log" if args.cmd == "ride" else None,
        force=True,  # fit_tool installs a stderr handler on import, which would garble curses
    )
    try:
        if args.cmd == "scan":
            asyncio.run(scan(args.seconds))
        elif args.cmd == "click-learn":
            asyncio.run(click_learn(os.environ["CLICK_ADDR"]))
        elif args.cmd == "ride":
            ride(args.zwo, out_dir, args.demo, args.speed if args.demo else 1.0)
        elif args.cmd == "export":
            export_fit(args.csv, args.csv.with_suffix(".fit"))
            print(args.csv.with_suffix(".fit"))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
