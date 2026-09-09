#!/usr/bin/env python3
"""SPARC — hardware discovery. READ-ONLY: moves nothing, drives nothing.

Run FIRST, on whichever Pi the Fusion HAT+ is mounted on:
    python3 00_discover.py

Answers: is the Fusion HAT+ alive on I2C? is the Hailo still alive alongside it?
is the IMX500 camera still enumerated? which GPIO/servo libs are usable?
"""
from __future__ import annotations
import shutil
import subprocess
import sys


def run(cmd: str) -> str:
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=25)
        return (p.stdout + p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return f"(failed: {e})"


def section(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


section("HOST")
print(run("hostname; cat /proc/device-tree/model 2>/dev/null; echo"))

section("I2C BUSES + DEVICES  (Fusion HAT+ should appear here)")
if not shutil.which("i2cdetect"):
    print("i2cdetect missing ->  sudo apt install -y i2c-tools")
else:
    buses = run("ls /dev/i2c-* 2>/dev/null")
    print(f"buses: {buses or '(none — enable I2C via raspi-config)'}")
    for bus in ("1", "0"):
        out = run(f"i2cdetect -y {bus} 2>/dev/null")
        if out and "Error" not in out:
            print(f"\n--- bus {bus} ---\n{out}")
print("""
Expected addresses if the Fusion HAT+ is alive:
  0x40  PCA9685 servo/PWM controller
  0x14/0x15  onboard GD32 MCU (SunFounder)
  0x68  MPU-6050 IMU (if fitted)
  0x40/0x41/0x44/0x45  INA260 (shares 0x40 with PCA9685 — check the jumper!)""")

section("HAILO  (must still work with the Fusion HAT+ installed)")
print(run("hailortcli fw-control identify 2>&1 | head -12") or "(hailortcli not found)")
print(run("lspci 2>/dev/null | grep -i hailo") or "(no Hailo on PCIe)")

section("CAMERA")
print(run("rpicam-hello --list-cameras 2>&1 | head -20") or "(rpicam-hello not found)")

section("PYTHON LIBS")
for mod in ("fusion_hat", "gpiozero", "lgpio", "smbus2", "board", "RPi.GPIO"):
    try:
        __import__(mod)
        print(f"  ✅ {mod}")
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ {mod}  ({type(e).__name__})")

section("FUSION_HAT API SURFACE  (so we script against what actually exists)")
try:
    import fusion_hat  # type: ignore
    names = [n for n in dir(fusion_hat) if not n.startswith("_")]
    print("  exports:", ", ".join(names))
    print("  file   :", getattr(fusion_hat, "__file__", "?"))
except Exception as e:  # noqa: BLE001
    print(f"  fusion_hat not importable: {e}")
    print("  install:  pip install fusion-hat   (or SunFounder's install script)")

section("GPIO IN USE")
print(run("cat /sys/kernel/debug/gpio 2>/dev/null | head -30") or "(needs sudo)")

print("\nDone. Paste this whole output back before running any servo test.")
