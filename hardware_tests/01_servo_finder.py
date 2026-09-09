#!/usr/bin/env python3
"""SPARC — pan/tilt servo finder. Identifies which channel is which, finds neutral.

SAFETY MODEL (the camera mount is fragile and the wiring is inaccessible):
  * nothing moves until you press a key
  * every move is a SMALL relative step (default 5 deg) from where we are
  * we start at 90 deg (mechanical mid) and never leave a configurable window
  * one channel at a time
  * Ctrl-C / 'q' detaches and leaves the servo where it stands

Run on the Pi that carries the Fusion HAT+:
    python3 01_servo_finder.py

Commands:  a/d = -/+ step    w/s = bigger/smaller step    c = go to 90
           n = mark this angle as NEUTRAL    p = pick another channel
           t = test sweep (small, guarded)   q = quit
"""
from __future__ import annotations
import sys

STEP_DEFAULT = 5
ANGLE_MIN, ANGLE_MAX = 40, 140     # deliberately narrow; widen only once mount is known
CHANNELS = [f"P{i}" for i in range(12)]

# ---------------------------------------------------------------- driver shim
# The exact fusion_hat API is version-dependent, so bind at runtime rather than
# assuming. Each candidate returns a callable set_angle(deg).

def make_servo(channel: str):
    import fusion_hat  # type: ignore

    # candidate 1: fusion_hat.Servo("P0").angle(deg)
    if hasattr(fusion_hat, "Servo"):
        try:
            s = fusion_hat.Servo(channel)
            for meth in ("angle", "set_angle", "write"):
                if hasattr(s, meth):
                    fn = getattr(s, meth)
                    return lambda deg, fn=fn: fn(deg), f"fusion_hat.Servo({channel}).{meth}()"
        except Exception as e:  # noqa: BLE001
            print(f"  Servo({channel}) failed: {e}")

    # candidate 2: fusion_hat.PWM / Pin-style
    if hasattr(fusion_hat, "PWM"):
        try:
            p = fusion_hat.PWM(channel)
            return lambda deg, p=p: p.pulse_width_time(500 + (deg / 180.0) * 2000), \
                   f"fusion_hat.PWM({channel}).pulse_width_time()"
        except Exception as e:  # noqa: BLE001
            print(f"  PWM({channel}) failed: {e}")

    raise RuntimeError(
        "No usable servo API found in fusion_hat. Run 00_discover.py and send me "
        "the 'FUSION_HAT API SURFACE' section so I can bind the right call."
    )


def getch() -> str:
    import termios, tty  # noqa: PLC0415
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def pick_channel() -> str:
    print(f"\nChannels: {', '.join(CHANNELS)}")
    print("Initial guess: pan=P2, tilt=P0  (unverified)")
    ch = input("channel [P0]: ").strip().upper() or "P0"
    return ch if ch in CHANNELS else "P0"


def main() -> None:
    print(__doc__)
    print("!! Watch the camera head. If anything binds or strains, hit Ctrl-C. !!")
    input("\nEnter to begin (nothing has moved yet)... ")

    channel = pick_channel()
    set_angle, how = make_servo(channel)
    print(f"  bound via {how}")

    angle, step = 90, STEP_DEFAULT
    neutrals: dict[str, int] = {}
    print(f"\nCentering {channel} to 90 deg — SMALL move, watch the head.")
    input("Enter to send 90 deg... ")
    set_angle(angle)

    while True:
        print(f"\r  {channel}  angle={angle:3d}  step={step:2d}   "
              f"[a/d move  w/s step  c 90  n neutral  p chan  t sweep  q quit] ",
              end="", flush=True)
        k = getch().lower()
        if k in ("q", "\x03"):
            break
        elif k == "a":
            angle = max(ANGLE_MIN, angle - step); set_angle(angle)
        elif k == "d":
            angle = min(ANGLE_MAX, angle + step); set_angle(angle)
        elif k == "w":
            step = min(20, step + 1)
        elif k == "s":
            step = max(1, step - 1)
        elif k == "c":
            angle = 90; set_angle(angle)
        elif k == "n":
            neutrals[channel] = angle
            print(f"\n  ** NEUTRAL for {channel} = {angle} deg **")
        elif k == "t":
            print("\n  small guarded sweep...")
            import time
            base = angle
            for d in (base - 10, base, base + 10, base):
                d = max(ANGLE_MIN, min(ANGLE_MAX, d))
                set_angle(d); print(f"    {d}"); time.sleep(0.6)
            angle = base; set_angle(angle)
        elif k == "p":
            print()
            channel = pick_channel()
            set_angle, how = make_servo(channel)
            print(f"  bound via {how}")
            angle = 90; input("Enter to center new channel... "); set_angle(angle)

    print("\n\n=== NEUTRALS FOUND ===")
    for ch, a in neutrals.items() or {}.items():
        print(f"  {ch}: {a} deg")
    if not neutrals:
        print("  (none marked)")
    print("Record which channel visually moved PAN (left/right) vs TILT (up/down).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\naborted — servo left where it stood.")
