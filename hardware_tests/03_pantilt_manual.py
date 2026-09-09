#!/usr/bin/env python3
"""SPARC — manual pan/tilt jog + safe-bounds finder.

Confirmed channels: TILT = P3, PAN = P1.

You drive. One keypress = one small step. Nothing sweeps, nothing loops, and the
script never commands a position you did not ask for.

    python3 03_pantilt_manual.py          # tilt=P3  pan=P1
    python3 03_pantilt_manual.py 3 1      # explicit  tilt pan

Keys
  w / s     tilt  - / +
  a / d     pan   - / +
  [ / ]     step size  1..15 deg
  z         slow glide back to 0,0
  1 / 2     record CURRENT tilt as tilt MIN / MAX
  3 / 4     record CURRENT pan  as pan  MIN / MAX
  p         print recorded bounds (copy-paste ready)
  L         toggle soft limit 45 <-> 90
  n / m     cycle tilt / pan channel (P0..P11)
  q         quit, leaving servos where they are

Angles are -90..+90 with 0 = mechanical centre (the full 180 of travel).
Soft limit starts at 45 to protect the mount; press L to unlock 90.
"""
from __future__ import annotations

import sys
import termios
import time
import tty

from fusion_hat import servo

STEP_DEFAULT = 2
SOFT_LIMIT = 45


def out(msg: str = "") -> None:
    sys.stdout.write(msg + "\r\n")
    sys.stdout.flush()


def getkey() -> str:
    """Blocking single-keypress read in raw mode. Returns '' on EOF."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class Axis:
    """One servo channel that owns its handle and can heal a failed write.

    The sysfs PWM handle can go stale (EINVAL on write) if a channel is rebound
    while an older Servo object still holds it. Rather than die, reopen once and
    retry — and always close the previous handle when switching channels.
    """

    def __init__(self, channel: int, name: str, invert: bool = False) -> None:
        self.name = name
        self.channel = channel
        self.invert = invert       # True when the servo is mounted mirrored
        self.pos = 0.0             # logical angle, in the direction the keys imply
        self.s = servo.Servo(channel)
        self.set(0.0)

    def set(self, deg: float) -> None:
        hw = -deg if self.invert else deg      # logical -> hardware
        try:
            self.s.angle(hw)
        except OSError:
            try:
                self.s.close()
            except Exception:  # noqa: BLE001
                pass
            self.s = servo.Servo(self.channel)   # reopen and retry once
            self.s.angle(hw)
        self.pos = deg

    def rebind(self, channel: int) -> None:
        try:
            self.s.close()
        except Exception:  # noqa: BLE001
            pass
        self.channel = channel
        self.s = servo.Servo(channel)
        self.set(0.0)


def glide(axis: "Axis", frm: float, to: float, name: str,
          step: float = 1.0, dwell: float = 0.04) -> float:
    d = frm
    while abs(d - to) > 0.51:
        d += step if to > d else -step
        axis.set(d)
        time.sleep(dwell)
    axis.set(to)
    out(f"  {name} glided to {to:+.0f}")
    return to


def main() -> None:
    # The #1 cause of this script exiting instantly: no TTY (missing `ssh -t`).
    if not sys.stdin.isatty():
        print("ERROR: stdin is not a terminal, so key input is impossible.")
        print("Re-run WITH the -t flag:")
        print("  ssh -t <user>@<vision-pi> 'python3 ~/03_pantilt_manual.py'")
        sys.exit(1)

    args = [int(a) for a in sys.argv[1:3]] if len(sys.argv) > 2 else [3, 1]
    tilt_ch, pan_ch = args[0], args[1]

    limit, step = SOFT_LIMIT, STEP_DEFAULT
    bounds: dict[str, float] = {}

    T = Axis(tilt_ch, "tilt")
    P = Axis(pan_ch, "pan")

    out(__doc__.split("Keys")[1].split("Angles")[0].rstrip())
    out(f"tilt=P{T.channel}  pan=P{P.channel}  — both at 0. Nothing moves until you press a key.")
    out("")

    while True:
        sys.stdout.write(
            f"\r  tilt P{T.channel} {T.pos:+6.1f}   pan P{P.channel} {P.pos:+6.1f}   "
            f"step {step:2d}   limit {limit}     "
        )
        sys.stdout.flush()

        try:
            k = getkey()
        except Exception as e:  # noqa: BLE001
            out(f"\ninput error: {e}")
            return
        if k == "":                       # EOF
            out("\nstdin closed — exiting.")
            return

        try:
            if k in ("q", "\x03"):
                out("\nquit — servos left as-is.")
                return
            elif k == "w":
                T.set(max(-limit, T.pos - step))
            elif k == "s":
                T.set(min(limit, T.pos + step))
            elif k == "a":
                P.set(max(-limit, P.pos - step))
            elif k == "d":
                P.set(min(limit, P.pos + step))
            elif k == "[":
                step = max(1, step - 1)
            elif k == "]":
                step = min(15, step + 1)
            elif k == "L":
                limit = 90 if limit == SOFT_LIMIT else SOFT_LIMIT
                out(f"\n  soft limit now +/-{limit}")
            elif k == "z":
                out("")
                glide(T, T.pos, 0.0, f"tilt P{T.channel}")
                glide(P, P.pos, 0.0, f"pan  P{P.channel}")
            elif k == "1":
                bounds["tilt_min"] = T.pos; out(f"\n  tilt MIN = {T.pos:+.0f}")
            elif k == "2":
                bounds["tilt_max"] = T.pos; out(f"\n  tilt MAX = {T.pos:+.0f}")
            elif k == "3":
                bounds["pan_min"] = P.pos;  out(f"\n  pan  MIN = {P.pos:+.0f}")
            elif k == "4":
                bounds["pan_max"] = P.pos;  out(f"\n  pan  MAX = {P.pos:+.0f}")
            elif k == "p":
                out("\n  --- recorded bounds ---")
                for key in ("tilt_min", "tilt_max", "pan_min", "pan_max"):
                    out(f"    {key}: {bounds.get(key, 'unset')}")
                tmin, tmax = bounds.get("tilt_min"), bounds.get("tilt_max")
                pmin, pmax = bounds.get("pan_min"), bounds.get("pan_max")
                if None not in (tmin, tmax):
                    out(f"    Servo({T.channel}, min={tmin:+.0f}, max={tmax:+.0f})   # tilt")
                if None not in (pmin, pmax):
                    out(f"    Servo({P.channel}, min={pmin:+.0f}, max={pmax:+.0f})   # pan")
            elif k == "n":
                T.rebind((T.channel + 1) % 12)
                out(f"\n  tilt channel -> P{T.channel}")
            elif k == "m":
                P.rebind((P.channel + 1) % 12)
                out(f"\n  pan channel -> P{P.channel}")
        except Exception as e:  # noqa: BLE001 — never let one bad key kill the session
            out(f"\n  !! error on key {k!r}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        out("\ninterrupted — servos left as-is.")
