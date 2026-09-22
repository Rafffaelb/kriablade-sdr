#!/usr/bin/env python3
"""
analyze_iq.py - Sanity-check, summarize, and plot a raw sc16q11 I/Q capture.

Usage:
    python3 analyze_iq.py capture1.sc16q11
    python3 analyze_iq.py capture1.sc16q11 --samplerate 2e6 --center-freq 915e6 \
        --fft-out spectrum.png

Works headless over SSH: the text summary always prints to stdout. The optional
spectrum plot is saved to a PNG file (matplotlib "Agg" backend, no display
needed) rather than shown interactively.

Two lessons learned during early KriaBlade testing are baked into this script
by default — see docs/FPGA_FIRMWARE_FIX.md and docs/SPECTRUM_ANALYSIS.md:

1. A capture can look statistically fine (I/Q means near zero, values in
   range) while badly corrupted at the hardware/firmware level. Early captures
   had ~75% of samples duplicated in fixed-size blocks due to a stale FPGA
   image on the bladeRF. This script always runs a duplicate-run check.

2. A single raw FFT is very noisy and can make a perfectly good signal look
   weak or hard to see. This script averages many overlapping FFT segments
   (Welch's method) by default, which is what actually makes a narrowband
   signal stand out from the noise floor in the saved plot.
"""
import argparse
import sys

import numpy as np


def load_sc16q11(path):
    data = np.fromfile(path, dtype=np.int16)
    if data.size % 2 != 0:
        print("Warning: odd number of int16 values; file may be truncated.", file=sys.stderr)
        data = data[: data.size - (data.size % 2)]
    i = data[0::2].astype(np.float32)
    q = data[1::2].astype(np.float32)
    return i, q


def summarize(i, q):
    mag = np.sqrt(i**2 + q**2)
    full_scale = 2048.0

    print(f"Total complex samples : {len(i)}")
    print(f"I range               : {i.min():.1f} to {i.max():.1f}")
    print(f"Q range               : {q.min():.1f} to {q.max():.1f}")
    print(f"I mean / Q mean       : {i.mean():.3f} / {q.mean():.3f}  (near 0 = healthy DC offset)")
    print(f"Magnitude mean / max  : {mag.mean():.2f} / {mag.max():.2f}")

    clipped = int(np.sum((np.abs(i) >= full_scale - 1) | (np.abs(q) >= full_scale - 1)))
    if clipped > 0:
        print(f"WARNING: {clipped} samples near full-scale (possible clipping) "
              f"— consider lowering --gain.")

    # Headroom hint: a very low peak relative to full scale usually means gain
    # could be increased for a stronger, easier-to-read signal without risking
    # clipping. See docs/SPECTRUM_ANALYSIS.md for the FM-band example where
    # 30 dB gain clipped and 10 dB gain used only ~19% of full scale.
    peak_frac = mag.max() / full_scale
    if peak_frac < 0.10 and clipped == 0:
        print(f"NOTE: peak amplitude is only {peak_frac*100:.1f}% of full scale. "
              f"There may be headroom to raise --gain for a stronger signal.")


def check_duplicate_runs(i, q, min_run=5):
    """
    Detect consecutive repeated (I, Q) pairs — a sign of a stuck/repeated
    buffer somewhere in the capture pipeline (bad FPGA image, USB stall, etc).
    A healthy capture of real RF noise should show ~0% samples in runs >= min_run.
    See docs/FPGA_FIRMWARE_FIX.md for the incident this check was written for.
    """
    i_int = i.astype(np.int64)
    q_int = q.astype(np.int64)
    same = (i_int[1:] == i_int[:-1]) & (q_int[1:] == q_int[:-1])

    run_lengths = []
    count = 0
    for s in same:
        if s:
            count += 1
        else:
            if count > 0:
                run_lengths.append(count)
            count = 0
    if count > 0:
        run_lengths.append(count)

    run_lengths = np.array(run_lengths, dtype=np.int64)
    n = len(i)
    dup_samples = int(run_lengths[run_lengths >= min_run].sum()) if len(run_lengths) else 0
    dup_frac = dup_samples / n if n else 0.0
    max_run = int(run_lengths.max()) if len(run_lengths) else 0

    print()
    print(f"Duplicate-run check (repeated I/Q pairs, run >= {min_run} samples):")
    print(f"  Duplicated fraction : {dup_frac * 100:.2f}%")
    print(f"  Max run length      : {max_run} samples")
    if dup_frac > 0.01:
        print("  WARNING: significant duplicated data detected. This capture is likely")
        print("  corrupted at the hardware/firmware level, not just noisy. See")
        print("  docs/FPGA_FIRMWARE_FIX.md — check 'bladeRF-cli -e version' for a")
        print("  firmware/FPGA version mismatch before trusting this data.")
    else:
        print("  OK — no significant duplicated-buffer pattern detected.")


def save_spectrum(i, q, samplerate, center_freq, out_path, nperseg=8192):
    """
    Plot an averaged (Welch) power spectral density, not a single raw FFT.
    A single FFT bin has high variance and makes real signals hard to see
    against the noise; averaging many overlapping segments smooths that out
    without hiding genuine narrowband content. See docs/SPECTRUM_ANALYSIS.md.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import welch

    iq = i.astype(np.float64) + 1j * q.astype(np.float64)
    n = len(iq)
    nperseg = min(nperseg, n)

    freqs, psd = welch(iq, fs=samplerate, nperseg=nperseg, noverlap=nperseg // 2,
                        window="hann", return_onesided=False, scaling="density")
    freqs = np.fft.fftshift(freqs)
    psd = np.fft.fftshift(psd)
    psd_db = 10 * np.log10(psd + 1e-20)

    if center_freq is not None:
        x = (center_freq + freqs) / 1e6
        xlabel = "Frequency (MHz)"
    else:
        x = freqs / 1e6
        xlabel = "Frequency offset (MHz)"

    peak_idx = np.argmax(psd_db)
    peak_db = psd_db[peak_idx]
    edge_frac = max(1, n // 20)
    noise_floor_db = np.median(np.concatenate([psd_db[:edge_frac], psd_db[-edge_frac:]]))

    plt.figure(figsize=(10, 5.5))
    plt.plot(x, psd_db, linewidth=1.2)
    plt.fill_between(x, psd_db, psd_db.min(), alpha=0.1, linewidth=0)
    plt.axhline(noise_floor_db, linestyle="--", linewidth=1, alpha=0.6)
    plt.xlabel(xlabel)
    plt.ylabel("Power spectral density (dB, arb. ref)")
    n_segments = max(1, n // (nperseg // 2))
    plt.title(f"Welch PSD — {n_segments:,} averaged segments (nperseg={nperseg})")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"Spectrum plot saved to {out_path}")
    print(f"Peak PSD: {peak_db:.1f} dB  |  Noise floor (band edges): {noise_floor_db:.1f} dB  "
          f"|  Peak SNR: {peak_db - noise_floor_db:.1f} dB")


def main():
    parser = argparse.ArgumentParser(description="Analyze a raw sc16q11 I/Q capture file.")
    parser.add_argument("path", help="Path to .sc16q11 capture file")
    parser.add_argument("--samplerate", type=float, default=2e6,
                         help="Sample rate used during capture, in Hz (default: 2e6)")
    parser.add_argument("--center-freq", type=float, default=None,
                         help="Center frequency in Hz, for labeling the spectrum plot's "
                              "x-axis in absolute terms instead of an offset (optional)")
    parser.add_argument("--fft-out", type=str, default=None,
                         help="If set, save a Welch-averaged spectrum plot to this PNG path")
    parser.add_argument("--nperseg", type=int, default=8192,
                         help="Welch segment length in samples (default: 8192). Larger = "
                              "finer frequency resolution but noisier; smaller = smoother "
                              "but coarser resolution.")
    parser.add_argument("--skip-duplicate-check", action="store_true",
                         help="Skip the repeated-buffer sanity check (not recommended)")
    args = parser.parse_args()

    i, q = load_sc16q11(args.path)
    summarize(i, q)

    if not args.skip_duplicate_check:
        check_duplicate_runs(i, q)

    if args.fft_out:
        save_spectrum(i, q, args.samplerate, args.center_freq, args.fft_out, args.nperseg)


if __name__ == "__main__":
    main()
