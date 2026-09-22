#!/usr/bin/env python3
"""
capture_iq.py - Parameterized I/Q capture wrapper around bladeRF-cli.

Usage:
    python3 capture_iq.py --freq 915e6 --samplerate 2e6 --gain 30 \
        --n 2000000 --out capture1.sc16q11

Requires bladeRF-cli on PATH and a bladeRF device accessible without root
(see docs/SETUP.md for the udev rule that makes this work as a normal user).
"""
import argparse
import shlex
import subprocess
import sys


def build_command(freq, samplerate, bandwidth, gain, n, out_file, channel="rx1"):
    chan_group = channel[:2]  # "rx1" -> "rx", "rx2" -> "rx"
    cmds = [
        f"set frequency {chan_group} {int(freq)}",
        f"set samplerate {chan_group} {int(samplerate)}",
        f"set bandwidth {chan_group} {int(bandwidth)}",
        f"set agc {chan_group} off",
        f"set gain {channel} {int(gain)}",
        f"rx config file={out_file} format=bin n={int(n)}",
        "rx start",
        "rx wait",
    ]
    return "; ".join(cmds)


def main():
    parser = argparse.ArgumentParser(description="Capture I/Q samples from a bladeRF device.")
    parser.add_argument("--freq", type=float, required=True,
                         help="Center frequency in Hz (e.g. 915e6)")
    parser.add_argument("--samplerate", type=float, default=2e6,
                         help="Sample rate in Hz (default: 2e6)")
    parser.add_argument("--bandwidth", type=float, default=None,
                         help="Filter bandwidth in Hz (default: same as samplerate)")
    parser.add_argument("--gain", type=int, default=30,
                         help="RX overall gain in dB (default: 30)")
    parser.add_argument("--n", type=int, default=2_000_000,
                         help="Number of complex samples to capture (default: 2,000,000)")
    parser.add_argument("--out", type=str, required=True,
                         help="Output file path (raw sc16q11 binary)")
    parser.add_argument("--channel", type=str, default="rx1", choices=["rx1", "rx2"],
                         help="RX channel (default: rx1)")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print the bladeRF-cli command without running it")
    args = parser.parse_args()

    bandwidth = args.bandwidth if args.bandwidth is not None else args.samplerate

    script = build_command(args.freq, args.samplerate, bandwidth, args.gain,
                            args.n, args.out, args.channel)
    cmd = ["bladeRF-cli", "-e", script]

    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    if args.dry_run:
        return

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"bladeRF-cli exited with code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    print(f"Capture complete: {args.out}")


if __name__ == "__main__":
    main()
