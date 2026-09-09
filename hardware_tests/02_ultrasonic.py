#!/usr/bin/env python3
"""SPARC — ultrasonic ranger test.  TRIG=GPIO27  ECHO=GPIO22 (verified working).

Raw lgpio implementation. gpiozero's DistanceSensor was tried first and blocked
without ever yielding a reading on this setup, so this drives the HC-SR04 directly:
10us trigger pulse, then time the echo high-pulse with a hard 60 ms timeout so a
missing echo reports cleanly instead of hanging.

Verified 2026-07-28 on the vision Pi: 5/5 trials, ~112.7 cm, <0.5 cm spread.
Echo idles LOW, so the input is safely level-shifted.

    python3 02_ultrasonic.py            # continuous, uses 27/22
    python3 02_ultrasonic.py 27 22      # explicit trig echo
"""
from __future__ import annotations
import sys
import time

import lgpio

TRIG = int(sys.argv[1]) if len(sys.argv) > 2 else 27
ECHO = int(sys.argv[2]) if len(sys.argv) > 2 else 22
TIMEOUT_S = 0.06          # 60 ms ~= 10 m, well past the sensor's 4 m range
SPEED_FACTOR = 17150      # cm per second of round-trip time


def measure(h: int) -> float | None:
    """One ranging cycle. Returns cm, or None if no echo came back."""
    lgpio.gpio_write(h, TRIG, 0)
    time.sleep(0.05)
    lgpio.gpio_write(h, TRIG, 1)
    time.sleep(0.00001)               # 10 us trigger
    lgpio.gpio_write(h, TRIG, 0)

    t0 = time.time()
    while time.time() - t0 < TIMEOUT_S:
        if lgpio.gpio_read(h, ECHO) == 1:
            break
    else:
        return None
    rise = time.time()
    while time.time() - rise < TIMEOUT_S and lgpio.gpio_read(h, ECHO) == 1:
        pass
    return (time.time() - rise) * SPEED_FACTOR


def main() -> None:
    print(f"ultrasonic: TRIG=GPIO{TRIG} ECHO=GPIO{ECHO}  (Ctrl-C to stop)")
    h = lgpio.gpiochip_open(0)
    n = bad = 0
    try:
        lgpio.gpio_claim_output(h, TRIG, 0)
        lgpio.gpio_claim_input(h, ECHO)
        print(f"echo idle state: {lgpio.gpio_read(h, ECHO)}  (0 = healthy)")
        print(f"{'#':>5} {'cm':>8}   bar")
        while True:
            n += 1
            cm = measure(h)
            if cm is None or cm > 400:
                bad += 1
                print(f"{n:>5} {'--':>8}   (no echo / out of range)")
            else:
                print(f"{n:>5} {cm:8.1f}   {'#' * min(50, int(cm / 4))}")
            time.sleep(0.4)
    except KeyboardInterrupt:
        print(f"\nstopped after {n} samples ({bad} bad).")
        if bad > n * 0.5:
            print("MOSTLY BAD -> check pin numbers, sensor 5V power, and wiring.")
    finally:
        lgpio.gpiochip_close(h)


if __name__ == "__main__":
    main()
